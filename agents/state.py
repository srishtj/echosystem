from typing import TypedDict, Literal, Optional
from pydantic import BaseModel


class AuditVerdict(BaseModel):
    status: Literal["pass", "fail"]
    reason: str
    flagged_claims: list[str]


class ResearchState(TypedDict):
    topic: str
    retrieved_context: list[dict]
    draft_report: str
    audit: Optional[AuditVerdict]
    retry_count: int
    final_report: Optional[str]
    input_tokens: int
    output_tokens: int
    flagged_claims_count: int


class AskState(TypedDict):
    question: str
    # draft_report/retrieved_context/audit/retry_count/final_report reuse the
    # exact field names ResearchState uses so agents.graph's auditor_node,
    # route_after_audit, finalize, and finalize_with_warning work unmodified.
    retrieved_context: list[dict]
    draft_report: str
    audit: Optional[AuditVerdict]
    retry_count: int
    final_report: Optional[str]
    input_tokens: int
    output_tokens: int
    flagged_claims_count: int
