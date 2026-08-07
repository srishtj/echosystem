import logging
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format=LOG_FORMAT)

REQUIRED_ENV_VARS = ["GROQ_API_KEY", "NEO4J_PASSWORD"]


def validate_required_env_vars():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in before starting EchoSystem-AI."
        )


validate_required_env_vars()

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_init, worker_process_init, beat_init


def _ensure_repo_root_on_path(*args, **kwargs):
    # Celery only keeps the repo root on sys.path during its own startup
    # module-loading window (celery.utils.imports.cwd_in_path). Modules that
    # get imported lazily inside a task body run after that window closes,
    # so we re-add it here on every process-lifecycle signal that matters.
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)


_ensure_repo_root_on_path()
worker_init.connect(_ensure_repo_root_on_path)
worker_process_init.connect(_ensure_repo_root_on_path)
beat_init.connect(_ensure_repo_root_on_path)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "echosystem",
    broker=f"{REDIS_URL}/0",
    backend=f"{REDIS_URL}/1",
    include=[
        "ingestion.tasks",
        "ingestion.digest",
        "extraction.tasks",
        "graph.ingest",
        "agents.tasks",
        "retrieval.embed",
        "retrieval.hybrid",
        "agents.graph",
    ],
)

celery_app.conf.worker_log_format = LOG_FORMAT
celery_app.conf.worker_task_log_format = LOG_FORMAT

celery_app.conf.beat_schedule = {
    # Generic feed polling (ingestion.tasks.poll_all_feeds) is intentionally not
    # scheduled here: it mixes unrelated topics into one graph. Ingestion is
    # driven on-demand by topic via ingestion.tasks.poll_topic (see /api/ingest).
    "run-research-cycle-every-30-min": {
        "task": "agents.tasks.run_research_cycle",
        "schedule": 1800.0,
    },
    "send-daily-digest": {
        "task": "ingestion.digest.send_daily_digest",
        "schedule": crontab(hour=8, minute=0),
    },
}