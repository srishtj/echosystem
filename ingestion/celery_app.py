from celery import Celery

celery_app = Celery(
    "echosystem",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=["ingestion.tasks"],
)

celery_app.conf.beat_schedule = {
    "poll-feeds-every-5-min" : {
        "task": "ingestion.tasks.poll_all_feeds",
        "schedule": 300.0,
    },
}