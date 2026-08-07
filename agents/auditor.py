import os
from dotenv import load_dotenv
load_dotenv()

import instructor
from groq import Groq
from agents.state import ResearchState, AuditVerdict

audit_client = instructor.from_groq(
    Groq(api_key=os.environ["GROQ_API_KEY"]), mode=instructor.Mode.JSON
)


def auditor_node(state: ResearchState) -> ResearchState:
    prompt = f"""You are a fact-checking editor. Compare this draft report against
the source context. Flag any claim NOT directly supported by the context,
and flag any claim that contradicts another part of the context. Default to
"fail" whenever a claim's support is ambiguous, not just when it is clearly false.

DRAFT:
{state['draft_report']}

SOURCE CONTEXT:
{state['retrieved_context']}
"""
    verdict: AuditVerdict = audit_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=AuditVerdict,
        max_retries=2,
        messages=[{"role": "user", "content": prompt}],
    )

    # instructor attaches the underlying completion (with token usage) to the
    # parsed model when available; tests that mock this call with a bare
    # AuditVerdict won't have it, so fall back to zero rather than erroring.
    raw = getattr(verdict, "_raw_response", None)
    input_tokens = raw.usage.prompt_tokens if raw and raw.usage else 0
    output_tokens = raw.usage.completion_tokens if raw and raw.usage else 0
    flagged_count = len(verdict.flagged_claims) if verdict.status == "fail" else 0

    return {
        **state,
        "audit": verdict,
        "retry_count": state.get("retry_count", 0) + 1,
        "input_tokens": state.get("input_tokens", 0) + input_tokens,
        "output_tokens": state.get("output_tokens", 0) + output_tokens,
        "flagged_claims_count": state.get("flagged_claims_count", 0) + flagged_count,
    }
