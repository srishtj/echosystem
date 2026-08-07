from unittest.mock import Mock

import agents.graph as agents_graph
import agents.tasks as agents_tasks
import ingestion.report_store as report_store


def test_run_research_cycle_skips_when_nothing_due(monkeypatch):
    monkeypatch.setattr(report_store, "get_watchlist_entries_due", lambda: [])
    run_research_and_persist = Mock()
    monkeypatch.setattr(agents_graph, "run_research_and_persist", run_research_and_persist)

    agents_tasks.run_research_cycle()

    run_research_and_persist.assert_not_called()


def test_run_research_cycle_researches_each_due_entry_and_marks_run(monkeypatch):
    due = [
        {"id": "e1", "type": "company", "value": "Acme Corp", "cadence": "daily"},
        {"id": "e2", "type": "topic", "value": "EV battery supply chain", "cadence": "weekly"},
    ]
    monkeypatch.setattr(report_store, "get_watchlist_entries_due", lambda: due)

    run_research_and_persist = Mock(return_value="report-id")
    monkeypatch.setattr(agents_graph, "run_research_and_persist", run_research_and_persist)

    mark_watchlist_run = Mock()
    monkeypatch.setattr(report_store, "mark_watchlist_run", mark_watchlist_run)

    agents_tasks.run_research_cycle()

    assert run_research_and_persist.call_args_list == [
        (("Acme Corp",),),
        (("EV battery supply chain",),),
    ]
    assert mark_watchlist_run.call_args_list == [(("e1",),), (("e2",),)]


def test_run_research_cycle_continues_after_one_entry_fails(monkeypatch):
    due = [
        {"id": "e1", "type": "company", "value": "Bad Co", "cadence": "daily"},
        {"id": "e2", "type": "company", "value": "Good Co", "cadence": "daily"},
    ]
    monkeypatch.setattr(report_store, "get_watchlist_entries_due", lambda: due)

    def fake_run(topic):
        if topic == "Bad Co":
            raise RuntimeError("groq quota exceeded")
        return "report-id"

    monkeypatch.setattr(agents_graph, "run_research_and_persist", fake_run)

    mark_watchlist_run = Mock()
    monkeypatch.setattr(report_store, "mark_watchlist_run", mark_watchlist_run)

    agents_tasks.run_research_cycle()

    # Failed entry never gets marked as run, so it stays due next cycle.
    mark_watchlist_run.assert_called_once_with("e2")
