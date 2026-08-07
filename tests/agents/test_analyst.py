import json
from unittest.mock import Mock

import agents.analyst as analyst
from agents import auditor
from agents.analyst import MAX_TOOL_ROUNDS, _call_tool, analyst_node, run_ask
from agents.state import AuditVerdict


def _tool_call(call_id: str, name: str, arguments: str):
    function = Mock()
    function.name = name
    function.arguments = arguments
    tc = Mock()
    tc.id = call_id
    tc.function = function
    return tc


def _response(content, tool_calls=None, prompt_tokens=100, completion_tokens=50):
    message = Mock()
    message.content = content
    message.tool_calls = tool_calls or []
    return Mock(
        choices=[Mock(message=message)],
        usage=Mock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def _base_state():
    return {
        "question": "How is Boeing doing?",
        "retrieved_context": [],
        "draft_report": "",
        "audit": None,
        "retry_count": 0,
        "final_report": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "flagged_claims_count": 0,
    }


def test_analyst_node_answers_without_tools(monkeypatch):
    monkeypatch.setattr(
        analyst.client.chat.completions,
        "create",
        Mock(return_value=_response("Boeing is a large aerospace company.")),
    )

    result = analyst_node(_base_state())

    assert result["draft_report"] == "Boeing is a large aerospace company."
    assert result["retrieved_context"] == []
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50


def test_analyst_node_calls_tool_then_answers(monkeypatch):
    monkeypatch.setattr(
        "retrieval.hybrid.hybrid_search",
        lambda query: [{"text": "Boeing claim", "score": 0.9, "graph_context": []}],
    )
    tool_call_response = _response(
        None, tool_calls=[_tool_call("call_1", "hybrid_search", '{"query": "Boeing"}')]
    )
    final_response = _response("Boeing's graph shows one recent claim.")
    monkeypatch.setattr(
        analyst.client.chat.completions,
        "create",
        Mock(side_effect=[tool_call_response, final_response]),
    )

    result = analyst_node(_base_state())

    assert result["draft_report"] == "Boeing's graph shows one recent claim."
    assert len(result["retrieved_context"]) == 1
    entry = result["retrieved_context"][0]
    assert entry["tool"] == "hybrid_search"
    assert entry["input"] == {"query": "Boeing"}
    assert json.loads(entry["output"])[0]["text"] == "Boeing claim"
    assert result["input_tokens"] == 200
    assert result["output_tokens"] == 100


def test_analyst_node_forces_synthesis_after_max_rounds(monkeypatch):
    monkeypatch.setattr("retrieval.hybrid.hybrid_search", lambda query: [])
    looping_response = _response(
        None, tool_calls=[_tool_call("call_1", "hybrid_search", '{"query": "Boeing"}')]
    )
    final_response = _response("Best effort answer after exhausting tool rounds.")
    responses = [looping_response] * MAX_TOOL_ROUNDS + [final_response]
    create_mock = Mock(side_effect=responses)
    monkeypatch.setattr(analyst.client.chat.completions, "create", create_mock)

    result = analyst_node(_base_state())

    assert result["draft_report"] == "Best effort answer after exhausting tool rounds."
    assert create_mock.call_count == MAX_TOOL_ROUNDS + 1
    # The final synthesis call must not offer tools, or the model could loop forever.
    final_call_kwargs = create_mock.call_args_list[-1].kwargs
    assert "tools" not in final_call_kwargs


def test_call_tool_handles_missing_reddit_credentials_gracefully(monkeypatch):
    def _raise_missing_creds(query, limit=10):
        raise KeyError("REDDIT_CLIENT_ID")

    monkeypatch.setattr("social.reddit.search_reddit", _raise_missing_creds)

    output = _call_tool("search_reddit", {"query": "Boeing"})

    assert "failed" in output.lower()
    assert "search_reddit" in output


def test_call_tool_unknown_tool_name():
    assert "Unknown tool" in _call_tool("not_a_real_tool", {"query": "x"})


def test_call_tool_no_match_returns_friendly_message(monkeypatch):
    monkeypatch.setattr("finance.stock.get_stock_data", lambda query: None)
    output = _call_tool("get_stock_data", {"query": "NotARealCompany"})
    assert "No stock data found" in output


def test_run_ask_pass_on_first_attempt_short_circuits(monkeypatch):
    monkeypatch.setattr(
        analyst.client.chat.completions,
        "create",
        Mock(return_value=_response("Boeing stock is up this week.")),
    )
    monkeypatch.setattr(
        auditor.audit_client.chat.completions,
        "create",
        Mock(return_value=AuditVerdict(status="pass", reason="ok", flagged_claims=[])),
    )

    result = run_ask("How is Boeing doing?")

    assert result["final_report"] == "Boeing stock is up this week."
    assert result["retry_count"] == 1
    assert result["audit"].status == "pass"


def test_run_ask_repeated_failures_trigger_finalize_with_warning(monkeypatch):
    monkeypatch.setattr(
        analyst.client.chat.completions,
        "create",
        Mock(return_value=_response("Boeing stock is up this week.")),
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

    result = run_ask("How is Boeing doing?")

    assert result["retry_count"] == 3
    assert "[UNVERIFIED" in result["final_report"]


def test_run_ask_fail_then_pass_finalizes_without_warning(monkeypatch):
    monkeypatch.setattr(
        analyst.client.chat.completions,
        "create",
        Mock(return_value=_response("Boeing stock is up this week.")),
    )
    verdicts = [
        AuditVerdict(status="fail", reason="unsupported claim", flagged_claims=["x"]),
        AuditVerdict(status="pass", reason="ok", flagged_claims=[]),
    ]
    monkeypatch.setattr(
        auditor.audit_client.chat.completions, "create", Mock(side_effect=verdicts)
    )

    result = run_ask("How is Boeing doing?")

    assert result["retry_count"] == 2
    assert "[UNVERIFIED" not in result["final_report"]
