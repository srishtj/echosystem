import json
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "reports.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            final_report TEXT NOT NULL,
            audit_status TEXT NOT NULL,
            retry_count INTEGER NOT NULL,
            created_at REAL NOT NULL,
            related_entities TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    try:
        conn.execute("ALTER TABLE reports ADD COLUMN related_entities TEXT NOT NULL DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            report_id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL NOT NULL,
            duration_seconds REAL NOT NULL,
            retry_count INTEGER NOT NULL,
            audit_status TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            flagged_claims_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            cadence TEXT NOT NULL,
            created_at REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            last_run_at REAL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_state (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
        """
    )

    return conn


def save_report(
    topic: str,
    final_report: str,
    audit_status: str,
    retry_count: int,
    related_entities: list[str] | None = None,
) -> str:
    report_id = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO reports "
            "(id, topic, final_report, audit_status, retry_count, created_at, related_entities) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                topic,
                final_report,
                audit_status,
                retry_count,
                time.time(),
                json.dumps(related_entities or []),
            ),
        )
    conn.close()
    return report_id


def load_recent_reports(limit: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, topic, final_report, audit_status, retry_count, created_at, related_entities "
        "FROM reports ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "topic": r[1],
            "final_report": r[2],
            "audit_status": r[3],
            "retry_count": r[4],
            "created_at": r[5],
            "related_entities": json.loads(r[6]),
        }
        for r in rows
    ]


def save_metrics(
    report_id: str,
    topic: str,
    started_at: float,
    finished_at: float,
    duration_seconds: float,
    retry_count: int,
    audit_status: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
    flagged_claims_count: int,
) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO metrics "
            "(report_id, topic, started_at, finished_at, duration_seconds, retry_count, "
            "audit_status, input_tokens, output_tokens, estimated_cost_usd, flagged_claims_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                topic,
                started_at,
                finished_at,
                duration_seconds,
                retry_count,
                audit_status,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                flagged_claims_count,
            ),
        )
    conn.close()


def get_stats() -> dict:
    conn = _connect()

    total_reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    (
        metrics_count,
        avg_duration,
        total_flagged_claims,
        reports_with_flags,
        reports_needing_retry,
        reports_recovered,
        total_estimated_cost,
    ) = conn.execute(
        "SELECT COUNT(*), AVG(duration_seconds), SUM(flagged_claims_count), "
        "SUM(CASE WHEN flagged_claims_count > 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN retry_count > 1 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN retry_count > 1 AND audit_status = 'pass' THEN 1 ELSE 0 END), "
        "SUM(estimated_cost_usd) "
        "FROM metrics"
    ).fetchone()

    audit_catch_rate = (reports_with_flags / metrics_count) if metrics_count else 0.0
    audit_recovery_rate = (
        (reports_recovered / reports_needing_retry) if reports_needing_retry else None
    )

    thirty_days_ago = time.time() - 30 * 86400
    daily_rows = conn.execute(
        "SELECT date(created_at, 'unixepoch') AS day, COUNT(*) "
        "FROM reports WHERE created_at >= ? GROUP BY day ORDER BY day",
        (thirty_days_ago,),
    ).fetchall()

    conn.close()

    return {
        "total_reports": total_reports,
        "avg_duration_seconds": avg_duration,
        "total_claims_flagged": total_flagged_claims or 0,
        "audit_catch_rate": audit_catch_rate,
        "audit_recovery_rate": audit_recovery_rate,
        "total_estimated_cost_usd": total_estimated_cost or 0.0,
        "reports_per_day": [{"date": row[0], "count": row[1]} for row in daily_rows],
    }


CADENCE_SECONDS = {"daily": 86400, "weekly": 7 * 86400}


def add_watchlist_entry(type_: str, value: str, cadence: str) -> str:
    entry_id = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO watchlist (id, type, value, cadence, created_at, active, last_run_at) "
            "VALUES (?, ?, ?, ?, ?, 1, NULL)",
            (entry_id, type_, value, cadence, time.time()),
        )
    conn.close()
    return entry_id


def list_watchlist(active_only: bool = False) -> list[dict]:
    conn = _connect()
    query = "SELECT id, type, value, cadence, created_at, active, last_run_at FROM watchlist"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "type": r[1],
            "value": r[2],
            "cadence": r[3],
            "created_at": r[4],
            "active": bool(r[5]),
            "last_run_at": r[6],
        }
        for r in rows
    ]


def delete_watchlist_entry(entry_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM watchlist WHERE id = ?", (entry_id,))
    conn.close()


def mark_watchlist_run(entry_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE watchlist SET last_run_at = ? WHERE id = ?", (time.time(), entry_id)
        )
    conn.close()


def get_watchlist_entries_due(now: float | None = None) -> list[dict]:
    """Active watchlist entries whose cadence window has elapsed since last_run_at."""
    now = now if now is not None else time.time()
    due = []
    for entry in list_watchlist(active_only=True):
        interval = CADENCE_SECONDS.get(entry["cadence"], CADENCE_SECONDS["daily"])
        if entry["last_run_at"] is None or now - entry["last_run_at"] >= interval:
            due.append(entry)
    return due


def get_last_digest_at() -> float | None:
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM digest_state WHERE key = 'last_digest_at'"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def set_last_digest_at(ts: float) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO digest_state (key, value) VALUES ('last_digest_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ts,),
        )
    conn.close()
