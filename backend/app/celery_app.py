"""Celery application factory for Glas Intelligence."""

import os
from celery import Celery


def make_celery():
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    celery = Celery(
        "glas_intelligence",
        broker=redis_url,
        backend=redis_url,
        include=[
            "app.tasks.graph_tasks",
            "app.tasks.simulation_tasks",
            "app.tasks.report_tasks",
            "app.tasks.pipeline_tasks",
            "app.tasks.research_tasks",
            "app.tasks.bundle_tasks",
        ],
    )

    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=3600,
        task_time_limit=3900,
        task_default_retry_delay=60,
        task_max_retries=3,
        broker_connection_retry_on_startup=True,
        task_routes={
            "glas.deep_research": {"queue": "research"},
            "glas.run_bundle": {"queue": "simulation"},
        },
        broker_transport_options={
            "priority_steps": list(range(10)),
            "queue_order_strategy": "priority",
        },
    )

    return celery


celery_app = make_celery()
