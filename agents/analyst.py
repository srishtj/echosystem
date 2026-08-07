import json
import os

from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from langgraph.graph import StateGraph, END

from agents.state import AskState
from agents.graph import auditor_node, route_after_audit, finalize, finalize_with_warning

client = Groq(api_key=os.environ["GROQ_API_KEY"])

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = (
    "You are a market research analyst. Answer the user's question using the "
    "available tools — search the knowledge graph, look up stock data, SEC "
    "filings, or Reddit discussion as needed. Call tools until you have enough "
    "grounded information, then give a final answer citing what you found. "
    "Every factual claim must be traceable to a tool result — do not invent "
    "figures or facts. If the tools don't have the answer, say so plainly."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "hybrid_search",
            "description": (
                "Search EchoSystem's knowledge graph and article index for claims "
                "and relationships about a company, person, or topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "A company, person, or topic name"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_data",
            "description": "Get current stock price, market cap, and 6-month price history for a public company.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Company name or ticker"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sec_snapshot",
            "description": (
                "Get SEC filing facts (revenue, net income, assets, liabilities) "
                "and recent filings for a US public company."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Company name or ticker"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_reddit",
            "description": "Search Reddit for recent discussion and sentiment about a company or topic.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
]


def _call_tool(name: str, args: dict) -> str:
    query = args.get("query", "")
    try:
        if name == "hybrid_search":
            from retrieval.hybrid import hybrid_search

            results = hybrid_search(query)
            return json.dumps(results[:5], default=str) if results else "No matches found in the knowledge graph."
        elif name == "get_stock_data":
            from finance.stock import get_stock_data

            data = get_stock_data(query)
            return json.dumps(data, default=str) if data else f"No stock data found for '{query}'."
        elif name == "get_sec_snapshot":
            from finance.sec import get_sec_snapshot

            data = get_sec_snapshot(query)
            return json.dumps(data, default=str) if data else f"No SEC filer found for '{query}'."
        elif name == "search_reddit":
            from social.reddit import search_reddit

            posts = search_reddit(query)
            return json.dumps(posts[:5], default=str) if posts else f"No Reddit discussion found for '{query}'."
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool '{name}' failed: {e}"


def analyst_node(state: AskState) -> AskState:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["question"]},
    ]

    if state.get("audit") and state["audit"].status == "fail":
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your previous answer was rejected: {state['audit'].reason}. "
                    f"Flagged claims: {state['audit'].flagged_claims}. "
                    f"Re-answer using ONLY facts returned by the tools."
                ),
            }
        )

    tool_results: list[dict] = []
    input_tokens = state.get("input_tokens", 0)
    output_tokens = state.get("output_tokens", 0)

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        input_tokens += resp.usage.prompt_tokens
        output_tokens += resp.usage.completion_tokens
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return {
                **state,
                "draft_report": msg.content or "",
                "retrieved_context": tool_results,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _call_tool(tc.function.name, args)
            tool_results.append({"tool": tc.function.name, "input": args, "output": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Exhausted tool rounds without a final answer — force a synthesis pass, no tools offered.
    messages.append(
        {"role": "user", "content": "Give your best final answer now, based only on the tool results above."}
    )
    resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages)
    input_tokens += resp.usage.prompt_tokens
    output_tokens += resp.usage.completion_tokens

    return {
        **state,
        "draft_report": resp.choices[0].message.content or "",
        "retrieved_context": tool_results,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


graph = StateGraph(AskState)
graph.add_node("analyst", analyst_node)
graph.add_node("auditor", auditor_node)
graph.add_node("finalize", finalize)
graph.add_node("finalize_with_warning", finalize_with_warning)

graph.set_entry_point("analyst")
graph.add_edge("analyst", "auditor")
graph.add_conditional_edges(
    "auditor",
    route_after_audit,
    {
        "finalize": "finalize",
        "finalize_with_warning": "finalize_with_warning",
        # route_after_audit's retry outcome is literally the string "researcher"
        # (agents.graph's node name) — map it to our retry node instead.
        "researcher": "analyst",
    },
)
graph.add_edge("finalize", END)
graph.add_edge("finalize_with_warning", END)

compiled_ask_graph = graph.compile()


def run_ask(question: str) -> AskState:
    return compiled_ask_graph.invoke(
        {
            "question": question,
            "retrieved_context": [],
            "draft_report": "",
            "audit": None,
            "retry_count": 0,
            "final_report": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "flagged_claims_count": 0,
        }
    )
