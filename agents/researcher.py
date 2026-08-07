import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from retrieval.hybrid import hybrid_search
from agents.state import ResearchState

client = Groq(api_key=os.environ["GROQ_API_KEY"])


def researcher_node(state: ResearchState) -> ResearchState:
    context = hybrid_search(state["topic"])

    feedback = ""
    if state.get("audit") and state["audit"].status == "fail":
        feedback = (
            f"Previous draft was rejected: {state['audit'].reason}. "
            f"Flagged claims: {state['audit'].flagged_claims}. "
            f"Rewrite using ONLY claims supported by the context below."
        )

    prompt = f"""You are a market analyst. Write a short report on: {state['topic']}

Source context:
{context}

{feedback}

Every factual claim must be traceable to the context above."""

    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        **state,
        "retrieved_context": context,
        "draft_report": resp.choices[0].message.content,
        "input_tokens": state.get("input_tokens", 0) + resp.usage.prompt_tokens,
        "output_tokens": state.get("output_tokens", 0) + resp.usage.completion_tokens,
    }
