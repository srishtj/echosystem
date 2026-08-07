import logging

from ingestion.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def run_research_cycle():
    from agents.graph import run_research_and_persist
    from ingestion.report_store import get_watchlist_entries_due, mark_watchlist_run

    due = get_watchlist_entries_due()
    if not due:
        logger.info("Research cycle: no watchlist entries due, skipping.")
        return

    for entry in due:
        try:
            run_research_and_persist(entry["value"])
            mark_watchlist_run(entry["id"])
        except Exception as e:
            logger.warning(
                "Research cycle failed for watchlist entry %r: %s", entry["value"], e
            )
