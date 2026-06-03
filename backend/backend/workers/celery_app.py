from celery import Celery

from backend.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "enterprise_ai_ats",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=30,
    task_routes={
        "backend.workers.tasks.parse_resume_task": {"queue": "ai"},
        "backend.workers.tasks.refresh_candidate_embeddings": {"queue": "ai"},
    },
)
