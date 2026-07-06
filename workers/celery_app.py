import os

from celery import Celery

from shared.logging_config import setup_logging

setup_logging("worker")

app = Celery(
    "enfila",
    broker=os.environ.get("RABBITMQ_URL", "amqp://enfila:enfila@localhost:5672/"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
