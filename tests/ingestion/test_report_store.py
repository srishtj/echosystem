import time

import pytest

from ingestion import report_store


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_reports.db")

    report_id = report_store.save_report(
        topic="Test Topic",
        final_report="This is the final report body.",
        audit_status="pass",
        retry_count=1,
        related_entities=["Acme", "Widget Co"],
    )

    reports = report_store.load_recent_reports()

    assert len(reports) == 1
    saved = reports[0]
    assert saved["id"] == report_id
    assert saved["topic"] == "Test Topic"
    assert saved["final_report"] == "This is the final report body."
    assert saved["audit_status"] == "pass"
    assert saved["retry_count"] == 1
    assert saved["related_entities"] == ["Acme", "Widget Co"]


def test_load_recent_reports_respects_limit_and_order(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_reports_ordering.db")

    for i in range(5):
        report_store.save_report(
            topic=f"Topic {i}",
            final_report=f"Report {i}",
            audit_status="pass",
            retry_count=0,
        )

    reports = report_store.load_recent_reports(limit=3)

    assert len(reports) == 3
    assert reports[0]["topic"] == "Topic 4"  # most recently saved comes first


def test_related_entities_defaults_to_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_reports_default.db")

    report_store.save_report(
        topic="No entities",
        final_report="...",
        audit_status="unknown",
        retry_count=0,
    )

    reports = report_store.load_recent_reports()
    assert reports[0]["related_entities"] == []


def _seed_metrics(report_id: str, topic: str, retry_count: int, audit_status: str,
                   duration_seconds: float, flagged_claims_count: int, cost: float):
    report_store.save_metrics(
        report_id=report_id,
        topic=topic,
        started_at=time.time() - duration_seconds,
        finished_at=time.time(),
        duration_seconds=duration_seconds,
        retry_count=retry_count,
        audit_status=audit_status,
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=cost,
        flagged_claims_count=flagged_claims_count,
    )


def test_save_metrics_round_trip_feeds_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_metrics.db")

    # Passed on first attempt: no flags, no retry needed.
    rid1 = report_store.save_report(
        topic="A", final_report="r1", audit_status="pass", retry_count=1
    )
    _seed_metrics(rid1, "A", retry_count=1, audit_status="pass",
                  duration_seconds=5, flagged_claims_count=0, cost=0.001)

    # Failed once, then recovered on retry.
    rid2 = report_store.save_report(
        topic="B", final_report="r2", audit_status="pass", retry_count=2
    )
    _seed_metrics(rid2, "B", retry_count=2, audit_status="pass",
                  duration_seconds=10, flagged_claims_count=2, cost=0.002)

    # Never recovered — exhausted retries.
    rid3 = report_store.save_report(
        topic="C", final_report="r3", audit_status="fail", retry_count=3
    )
    _seed_metrics(rid3, "C", retry_count=3, audit_status="fail",
                  duration_seconds=15, flagged_claims_count=3, cost=0.003)

    stats = report_store.get_stats()

    assert stats["total_reports"] == 3
    assert stats["avg_duration_seconds"] == pytest.approx(10.0)
    assert stats["total_claims_flagged"] == 5
    assert stats["audit_catch_rate"] == pytest.approx(2 / 3)  # B and C had flags
    assert stats["audit_recovery_rate"] == pytest.approx(0.5)  # of {B, C}, only B recovered
    assert stats["total_estimated_cost_usd"] == pytest.approx(0.006)
    assert stats["reports_per_day"][0]["count"] == 3


def test_get_stats_with_no_data_returns_zeroed_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_metrics_empty.db")

    stats = report_store.get_stats()

    assert stats["total_reports"] == 0
    assert stats["total_claims_flagged"] == 0
    assert stats["audit_catch_rate"] == 0.0
    assert stats["audit_recovery_rate"] is None  # no reports ever needed a retry
    assert stats["reports_per_day"] == []


def test_add_list_delete_watchlist_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_watchlist.db")

    entry_id = report_store.add_watchlist_entry("company", "Acme Corp", "daily")

    entries = report_store.list_watchlist()
    assert len(entries) == 1
    assert entries[0]["id"] == entry_id
    assert entries[0]["type"] == "company"
    assert entries[0]["value"] == "Acme Corp"
    assert entries[0]["cadence"] == "daily"
    assert entries[0]["active"] is True
    assert entries[0]["last_run_at"] is None

    report_store.delete_watchlist_entry(entry_id)
    assert report_store.list_watchlist() == []


def test_get_watchlist_entries_due_never_run_is_always_due(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_watchlist_due.db")

    report_store.add_watchlist_entry("company", "Acme Corp", "daily")

    due = report_store.get_watchlist_entries_due()
    assert len(due) == 1
    assert due[0]["value"] == "Acme Corp"


def test_get_watchlist_entries_due_respects_cadence(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_watchlist_cadence.db")

    daily_id = report_store.add_watchlist_entry("company", "Daily Co", "daily")
    weekly_id = report_store.add_watchlist_entry("topic", "Weekly Topic", "weekly")

    report_store.mark_watchlist_run(daily_id)
    report_store.mark_watchlist_run(weekly_id)

    now = time.time()
    two_days_later = now + 2 * 86400

    due = report_store.get_watchlist_entries_due(now=two_days_later)

    due_values = {e["value"] for e in due}
    assert due_values == {"Daily Co"}  # weekly entry not due yet, daily is overdue


def test_last_digest_at_defaults_to_none_then_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(report_store, "DB_PATH", tmp_path / "test_digest_state.db")

    assert report_store.get_last_digest_at() is None

    report_store.set_last_digest_at(12345.0)
    assert report_store.get_last_digest_at() == 12345.0

    report_store.set_last_digest_at(67890.0)
    assert report_store.get_last_digest_at() == 67890.0
