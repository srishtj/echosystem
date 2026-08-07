from unittest.mock import Mock

import pytest

import agents.graph as agents_graph
from agents import researcher, auditor
from agents.graph import (
    run_research,
    run_research_and_persist,
    MAX_RETRIES,
    estimate_cost_usd,
    COST_PER_MILLION_INPUT_TOKENS_USD,
    COST_PER_MILLION_OUTPUT_TOKENS_USD,
)
from agents.state import AuditVerdict


def _fake_context():
    return [{"text": "Some article text", "score": 0.9, "graph_context": []}]


def test_estimate_cost_usd_zero_tokens_is_free():
    assert estimate_cost_usd(0, 0) == 0.0


def test_estimate_cost_usd_scales_with_tokens():
    cost = estimate_cost_usd(1_000_000, 1_000_000)
    expected = COST_PER_MILLION_INPUT_TOKENS_USD + COST_PER_MILLION_OUTPUT_TOKENS_USD
    assert cost == pytest.approx(expected)


def test_estimate_cost_usd_input_and_output_priced_independently():
    input_only = estimate_cost_usd(1_000_000, 0)
    output_only = estimate_cost_usd(0, 1_000_000)
    assert input_only == pytest.approx(COST_PER_MILLION_INPUT_TOKENS_USD)
    assert output_only == pytest.approx(COST_PER_MILLION_OUTPUT_TOKENS_USD)


def _fake_researcher_response(content: str):
    return Mock(
        choices=[Mock(message=Mock(content=content))],
        usage=Mock(prompt_tokens=100, completion_tokens=50),
    )


def test_pass_on_first_attempt_short_circuits(monkeypatch):
    monkeypatch.setattr(researcher, "hybrid_search", lambda topic: _fake_context())
    monkeypatch.setattr(
        researcher.client.chat.completions,
        "create",
        Mock(return_value=_fake_researcher_response("Draft report content")),
    )
    monkeypatch.setattr(
        auditor.audit_client.chat.completions,
        "create",
        Mock(return_value=AuditVerdict(status="pass", reason="ok", flagged_claims=[])),
    )

    result = run_research("test topic")

    assert result["final_report"] == "Draft report content"
    assert result["retry_count"] == 1
    assert result["audit"].status == "pass"
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["flagged_claims_count"] == 0


def test_repeated_failures_trigger_finalize_with_warning(monkeypatch):
    monkeypatch.setattr(researcher, "hybrid_search", lambda topic: _fake_context())
    monkeypatch.setattr(
        researcher.client.chat.completions,
        "create",
        Mock(return_value=_fake_researcher_response("Draft report content")),
    )
    monkeypatch.setattr(
        auditor.audit_client.chat.completions,
        "create",
        Mock(
            return_value=AuditVerdict(
                status="fail", reason="unsupported claim", flagged_claims=["x"]
            )
        ),
    )

    result = run_research("test topic")

    assert result["retry_count"] == MAX_RETRIES
    assert result["audit"].status == "fail"
    assert "[UNVERIFIED" in result["final_report"]
    assert result["input_tokens"] == 100 * MAX_RETRIES
    assert result["output_tokens"] == 50 * MAX_RETRIES
    assert result["flagged_claims_count"] == MAX_RETRIES  # one flagged claim per failed attempt


def test_fail_then_pass_finalizes_without_warning(monkeypatch):
    monkeypatch.setattr(researcher, "hybrid_search", lambda topic: _fake_context())
    monkeypatch.setattr(
        researcher.client.chat.completions,
        "create",
        Mock(return_value=_fake_researcher_response("Draft report content")),
    )
    verdicts = [
        AuditVerdict(status="fail", reason="unsupported claim", flagged_claims=["x"]),
        AuditVerdict(status="pass", reason="ok", flagged_claims=[]),
    ]
    monkeypatch.setattr(
        auditor.audit_client.chat.completions,
        "create",
        Mock(side_effect=verdicts),
    )

    result = run_research("test topic")

    assert result["retry_count"] == 2
    assert result["audit"].status == "pass"
    assert "[UNVERIFIED" not in result["final_report"]
    assert result["flagged_claims_count"] == 1  # only the first (failed) attempt flagged anything


def test_run_research_and_persist_saves_report_and_metrics(tmp_path, monkeypatch):
    import graph.ingest as graph_ingest
    from ingestion import report_store

    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_persist.db")
    monkeypatch.setattr(graph_ingest, "find_mentioned_entities", lambda text: ["Acme"])

    fake_result = {
        "topic": "Acme Corp",
        "final_report": "Acme Corp is doing well.",
        "audit": AuditVerdict(status="pass", reason="ok", flagged_claims=[]),
        "retry_count": 1,
        "input_tokens": 123,
        "output_tokens": 45,
        "flagged_claims_count": 0,
    }
    monkeypatch.setattr(agents_graph, "run_research", lambda topic: fake_result)

    report_id = run_research_and_persist("Acme Corp")

    reports = report_store.load_recent_reports()
    assert len(reports) == 1
    assert reports[0]["id"] == report_id
    assert reports[0]["topic"] == "Acme Corp"
    assert reports[0]["final_report"] == "Acme Corp is doing well."
    assert reports[0]["related_entities"] == ["Acme"]

    stats = report_store.get_stats()
    assert stats["total_reports"] == 1
    assert stats["total_estimated_cost_usd"] == pytest.approx(estimate_cost_usd(123, 45))
