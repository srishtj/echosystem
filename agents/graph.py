import os
import time

from langgraph.graph import StateGraph, END
from agents.state import ResearchState
from agents.researcher import researcher_node
from agents.auditor import auditor_node

MAX_RETRIES = 3

# Approximate reference pricing (USD per 1M tokens), used only to estimate what
# this run *would* cost on a representative paid hosted-LLM tier — actual usage
# on Groq's free tier costs $0. Override via env vars if you have more precise
# current pricing for the model you're comparing against.
COST_PER_MILLION_INPUT_TOKENS_USD = float(os.environ.get("COST_PER_M_INPUT_TOKENS_USD", "0.59"))
COST_PER_MILLION_OUTPUT_TOKENS_USD = float(os.environ.get("COST_PER_M_OUTPUT_TOKENS_USD", "0.79"))


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * COST_PER_MILLION_INPUT_TOKENS_USD
        + output_tokens / 1_000_000 * COST_PER_MILLION_OUTPUT_TOKENS_USD
    )


def route_after_audit(state: ResearchState) -> str:
    if state["audit"].status == "pass":
        return "finalize"
    if state["retry_count"] >= MAX_RETRIES:
        return "finalize_with_warning"
    return "researcher"


def finalize(state: ResearchState) -> ResearchState:
    return {**state, "final_report": state["draft_report"]}


def finalize_with_warning(state: ResearchState) -> ResearchState:
    note = "\n\n[UNVERIFIED: failed audit after 3 attempts. Review manually.]"
    return {**state, "final_report": state["draft_report"] + note}


graph = StateGraph(ResearchState)
graph.add_node("researcher", researcher_node)
graph.add_node("auditor", auditor_node)
graph.add_node("finalize", finalize)
graph.add_node("finalize_with_warning", finalize_with_warning)

graph.set_entry_point("researcher")
graph.add_edge("researcher", "auditor")
graph.add_conditional_edges("auditor", route_after_audit, {
    "finalize": "finalize",
    "finalize_with_warning": "finalize_with_warning",
    "researcher": "researcher",
})
graph.add_edge("finalize", END)
graph.add_edge("finalize_with_warning", END)

compiled_graph = graph.compile()


def run_research(topic: str) -> ResearchState:
    return compiled_graph.invoke({
        "topic": topic,
        "retry_count": 0,
        "audit": None,
        "draft_report": "",
        "final_report": None,
        "retrieved_context": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "flagged_claims_count": 0,
    })


def run_research_and_persist(topic: str) -> str:
    """Run the Critic Loop for `topic` and persist both the report and its
    metrics under the same report_id. Single choke point so every caller
    (topic search, the scheduled research cycle) gets metrics for free."""
    from graph.ingest import find_mentioned_entities
    from ingestion.report_store import save_metrics, save_report

    started_at = time.time()
    result = run_research(topic)
    finished_at = time.time()

    audit = result.get("audit")
    audit_status = audit.status if audit else "unknown"
    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)

    report_id = save_report(
        topic=topic,
        final_report=result["final_report"],
        audit_status=audit_status,
        retry_count=result["retry_count"],
        related_entities=find_mentioned_entities(result["final_report"]),
    )

    save_metrics(
        report_id=report_id,
        topic=topic,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=finished_at - started_at,
        retry_count=result["retry_count"],
        audit_status=audit_status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(input_tokens, output_tokens),
        flagged_claims_count=result.get("flagged_claims_count", 0),
    )

    return report_id
