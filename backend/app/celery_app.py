"""Celery application factory for Glas Intelligence."""

import os
from celery import Celery
from .config import Config

def make_celery():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    celery = Celery(
        'glas_intelligence',
        broker=redis_url,
        backend=redis_url,
        include=[
            'app.tasks.graph_tasks',
            'app.tasks.simulation_tasks',
            'app.tasks.report_tasks',
            'app.tasks.pipeline_tasks',
        ],
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=3600,
        task_time_limit=3900,
        task_default_retry_delay=60,
        task_max_retries=3,
        broker_connection_retry_on_startup=True,
    )
    
    return celery

celery_app = make_celery()
