import time
from unittest.mock import MagicMock, Mock

import ingestion.digest as digest
import ingestion.report_store as report_store
import finance.stock as stock
import finance.sec as sec


def _fake_neo4j_driver(contradiction_count: int):
    session = MagicMock()
    session.run.return_value.single.return_value = {"c": contradiction_count}
    session.__enter__.return_value = session
    driver = MagicMock()
    driver.session.return_value = session
    return driver


def test_build_digest_includes_entity_with_new_report(monkeypatch):
    monkeypatch.setattr(
        report_store, "list_watchlist", lambda active_only=False: [
            {"id": "e1", "type": "company", "value": "Acme Corp", "cadence": "daily"}
        ]
    )
    since = time.time() - 3600
    monkeypatch.setattr(
        report_store, "load_recent_reports", lambda limit=100: [
            {
                "id": "r1",
                "topic": "Acme Corp",
                "audit_status": "pass",
                "created_at": since + 100,
                "related_entities": ["Acme Corp"],
            }
        ]
    )
    monkeypatch.setattr(digest, "driver", _fake_neo4j_driver(0))
    monkeypatch.setattr(digest, "_notable_stock_move", lambda entity: None)
    monkeypatch.setattr(digest, "_new_filings_for", lambda entity, since: [])

    result = digest.build_digest(since=since)

    assert len(result["sections"]) == 1
    assert result["sections"][0]["entity"] == "Acme Corp"
    assert len(result["sections"][0]["new_reports"]) == 1


def test_build_digest_excludes_entity_with_nothing_new(monkeypatch):
    monkeypatch.setattr(
        report_store, "list_watchlist", lambda active_only=False: [
            {"id": "e1", "type": "company", "value": "Quiet Co", "cadence": "daily"}
        ]
    )
    monkeypatch.setattr(report_store, "load_recent_reports", lambda limit=100: [])
    monkeypatch.setattr(digest, "driver", _fake_neo4j_driver(0))
    monkeypatch.setattr(digest, "_notable_stock_move", lambda entity: None)
    monkeypatch.setattr(digest, "_new_filings_for", lambda entity, since: [])

    result = digest.build_digest(since=time.time() - 3600)

    assert result["sections"] == []


def test_build_digest_topic_entries_skip_stock_and_sec_lookups(monkeypatch):
    monkeypatch.setattr(
        report_store, "list_watchlist", lambda active_only=False: [
            {"id": "e1", "type": "topic", "value": "EV battery supply chain", "cadence": "weekly"}
        ]
    )
    monkeypatch.setattr(report_store, "load_recent_reports", lambda limit=100: [])
    monkeypatch.setattr(digest, "driver", _fake_neo4j_driver(1))

    stock_move = Mock()
    filings = Mock()
    monkeypatch.setattr(digest, "_notable_stock_move", stock_move)
    monkeypatch.setattr(digest, "_new_filings_for", filings)

    result = digest.build_digest(since=time.time() - 3600)

    stock_move.assert_not_called()
    filings.assert_not_called()
    assert len(result["sections"]) == 1  # still included via the contradiction count


def test_notable_stock_move_below_threshold_returns_none(monkeypatch):
    monkeypatch.setattr(stock, "get_stock_data", lambda q: {"symbol": "ACME", "change_percent": 2.0})
    assert digest._notable_stock_move("Acme Corp") is None


def test_notable_stock_move_above_threshold_returns_move(monkeypatch):
    monkeypatch.setattr(stock, "get_stock_data", lambda q: {"symbol": "ACME", "change_percent": -7.5})
    move = digest._notable_stock_move("Acme Corp")
    assert move == {"symbol": "ACME", "change_percent": -7.5}


def test_new_filings_for_filters_by_date(monkeypatch):
    monkeypatch.setattr(
        sec, "get_sec_snapshot", lambda q: {
            "filings": [
                {"form": "10-K", "filed": "2020-01-01"},
                {"form": "8-K", "filed": "2099-01-01"},
            ]
        }
    )
    since = time.mktime(time.strptime("2050-01-01", "%Y-%m-%d"))
    filings = digest._new_filings_for("Acme Corp", since)
    assert len(filings) == 1
    assert filings[0]["form"] == "8-K"


def test_send_digest_without_webhook_does_not_advance_last_digest_at(monkeypatch):
    monkeypatch.setattr(digest, "SLACK_WEBHOOK_URL", None)
    monkeypatch.setattr(
        digest, "build_digest", lambda: {
            "since": 0,
            "sections": [{"entity": "Acme Corp", "new_reports": [{"topic": "x", "audit_status": "pass"}],
                          "new_contradictions": 0, "stock_move": None, "new_filings": []}],
        }
    )
    set_last_digest_at = Mock()
    monkeypatch.setattr(report_store, "set_last_digest_at", set_last_digest_at)

    sent = digest.send_digest()

    assert sent is False
    set_last_digest_at.assert_not_called()


def test_send_digest_with_nothing_new_still_advances_last_digest_at(monkeypatch):
    monkeypatch.setattr(digest, "build_digest", lambda: {"since": 0, "sections": []})
    set_last_digest_at = Mock()
    monkeypatch.setattr(report_store, "set_last_digest_at", set_last_digest_at)

    sent = digest.send_digest()

    assert sent is False
    set_last_digest_at.assert_called_once()


def test_send_digest_with_webhook_posts_and_advances_last_digest_at(monkeypatch):
    monkeypatch.setattr(digest, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/fake")
    monkeypatch.setattr(
        digest, "build_digest", lambda: {
            "since": 0,
            "sections": [{"entity": "Acme Corp", "new_reports": [{"topic": "x", "audit_status": "pass"}],
                          "new_contradictions": 2, "stock_move": {"symbol": "ACME", "change_percent": 6.0},
                          "new_filings": [{"form": "8-K", "filed": "2026-08-01"}]}],
        }
    )
    fake_response = Mock()
    fake_response.raise_for_status = Mock()
    post = Mock(return_value=fake_response)
    monkeypatch.setattr(digest.httpx, "post", post)
    set_last_digest_at = Mock()
    monkeypatch.setattr(report_store, "set_last_digest_at", set_last_digest_at)

    sent = digest.send_digest()

    assert sent is True
    post.assert_called_once()
    sent_message = post.call_args.kwargs["json"]["text"]
    assert "Acme Corp" in sent_message
    assert "2 new contradiction" in sent_message
    set_last_digest_at.assert_called_once()
