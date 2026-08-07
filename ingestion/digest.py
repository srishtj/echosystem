import logging
import os
import time

import httpx
from dotenv import load_dotenv
load_dotenv()

from graph.ingest import driver
from ingestion.celery_app import celery_app

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DEFAULT_WINDOW_SECONDS = 24 * 3600
STOCK_MOVE_THRESHOLD_PERCENT = 5


def _new_reports_for(entity: str, since: float) -> list[dict]:
    from ingestion.report_store import load_recent_reports

    return [
        r
        for r in load_recent_reports(limit=100)
        if r["created_at"] >= since and entity in r["related_entities"]
    ]


def _new_contradiction_count(entity: str, since_ms: float) -> int:
    with driver.session() as session:
        result = session.run(
            "MATCH (n:Entity {name: $name})-[:CLAIM]->(c:Claim)-[r:CONTRADICTS]-(:Claim) "
            "WHERE r.detected_at >= $since_ms "
            "RETURN count(DISTINCT r) AS c",
            name=entity,
            since_ms=since_ms,
        ).single()
        return result["c"] if result else 0


def _notable_stock_move(entity: str) -> dict | None:
    from finance.stock import get_stock_data

    try:
        data = get_stock_data(entity)
    except Exception as e:
        logger.debug("Digest stock lookup skipped for %r: %s", entity, e)
        return None
    if not data or data.get("change_percent") is None:
        return None
    change = data["change_percent"]
    if abs(change) < STOCK_MOVE_THRESHOLD_PERCENT:
        return None
    return {"symbol": data["symbol"], "change_percent": round(change, 2)}


def _new_filings_for(entity: str, since: float) -> list[dict]:
    from finance.sec import get_sec_snapshot

    try:
        data = get_sec_snapshot(entity)
    except Exception as e:
        logger.debug("Digest SEC lookup skipped for %r: %s", entity, e)
        return []
    if not data:
        return []
    cutoff_date = time.strftime("%Y-%m-%d", time.gmtime(since))
    return [f for f in data["filings"] if f.get("filed") and f["filed"] >= cutoff_date]


def build_digest(since: float | None = None) -> dict:
    """Compile what's new for each active watchlist entry since `since`
    (defaults to the last successfully-sent digest, or 24h ago on first run)."""
    from ingestion.report_store import get_last_digest_at, list_watchlist

    if since is None:
        since = get_last_digest_at()
        if since is None:
            since = time.time() - DEFAULT_WINDOW_SECONDS
    since_ms = since * 1000

    sections = []
    for entry in list_watchlist(active_only=True):
        name = entry["value"]
        new_reports = _new_reports_for(name, since)
        contradiction_count = _new_contradiction_count(name, since_ms)
        stock_move = _notable_stock_move(name) if entry["type"] == "company" else None
        new_filings = _new_filings_for(name, since) if entry["type"] == "company" else []

        if not (new_reports or contradiction_count or stock_move or new_filings):
            continue

        sections.append(
            {
                "entity": name,
                "new_reports": new_reports,
                "new_contradictions": contradiction_count,
                "stock_move": stock_move,
                "new_filings": new_filings,
            }
        )

    return {"since": since, "sections": sections}


def _format_slack_message(digest: dict) -> str | None:
    if not digest["sections"]:
        return None
    lines = ["*EchoSystem-AI Daily Digest*"]
    for section in digest["sections"]:
        lines.append(f"\n*{section['entity']}*")
        for r in section["new_reports"]:
            lines.append(f"  • New report: {r['topic']} ({r['audit_status']})")
        if section["new_contradictions"]:
            lines.append(
                f"  • {section['new_contradictions']} new contradiction(s) surfaced"
            )
        if section["stock_move"]:
            move = section["stock_move"]
            lines.append(f"  • Stock moved {move['change_percent']}% ({move['symbol']})")
        for f in section["new_filings"]:
            lines.append(f"  • New {f['form']} filing ({f['filed']})")
    return "\n".join(lines)


def send_digest() -> bool:
    """Compile and send the daily digest. Returns True if a digest was actually sent."""
    from ingestion.report_store import set_last_digest_at

    digest = build_digest()
    message = _format_slack_message(digest)

    if not message:
        logger.info("Digest: nothing new for any watchlist entity, skipping send.")
        set_last_digest_at(time.time())
        return False

    if not SLACK_WEBHOOK_URL:
        logger.warning(
            "Digest ready but SLACK_WEBHOOK_URL is not set — skipping send. "
            "Set it in .env to actually deliver digests. Digest content:\n%s",
            message,
        )
        return False

    resp = httpx.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=10)
    resp.raise_for_status()
    set_last_digest_at(time.time())
    logger.info("Digest sent to Slack (%d entities with updates).", len(digest["sections"]))
    return True


@celery_app.task
def send_daily_digest():
    try:
        send_digest()
    except Exception as e:
        logger.warning("Daily digest failed: %s", e)
