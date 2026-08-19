import os

from celery import Celery
from celery.signals import worker_ready
from kombu import Queue
from prometheus_client import start_http_server

from shared.logging_config import setup_logging

setup_logging("worker")

app = Celery(
    "enfila",
    broker=os.environ["RABBITMQ_URL"],
    backend=os.environ["REDIS_URL"],
    include=["workers.inference_task", "workers.webhook_task"],
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
    task_default_queue="inference.dispatch",
    task_default_exchange="",
    task_default_routing_key="inference.dispatch",
    task_queues=(
        Queue(
            "inference.dispatch",
            routing_key="inference.dispatch",
            queue_arguments={"x-queue-type": "quorum"},
        ),
        Queue(
            "webhooks.delivery",
            routing_key="webhooks.delivery",
            queue_arguments={"x-queue-type": "quorum"},
        ),
    ),
    broker_transport_options={"confirm_publish": True},
)


@worker_ready.connect  # type: ignore[untyped-decorator]
def start_worker_metrics(**_: object) -> None:  # pragma: no cover
    start_http_server(int(os.environ.get("WORKER_METRICS_PORT", "9100")))
