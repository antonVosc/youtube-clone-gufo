from celery import Celery

from app.config import settings
from app.transcode import cleanup_stale_uploads as run
from app.transcode import process_video

celery_app = Celery("tube", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=4000,
    beat_schedule={
        "cleanup-stale-uploads": {"task": "cleanup_stale_uploads", "schedule": 3600.0}
    },
)


@celery_app.task(
    name="transcode_video", autoretry_for=OSError, retry_backoff=True, max_retries=3
)
def transcode_video(video_id):
    process_video(video_id)


@celery_app.task(name="cleanup_stale_uploads")
def cleanup_stale_uploads():
    return run()
