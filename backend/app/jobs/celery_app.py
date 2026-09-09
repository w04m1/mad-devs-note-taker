from celery import Celery

from app.config import get_settings
from app.jobs import maintenance, outbox, reminders

settings = get_settings()
celery_app = Celery("notetaker", broker=settings.celery_broker_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    enable_utc=True,
    timezone="UTC",
    task_acks_late=False,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "discover-due-reminders": {
            "task": "app.jobs.scan_due",
            "schedule": float(settings.reminder_scan_interval_seconds),
        },
        "publish-outbox": {
            "task": "app.jobs.publish_outbox",
            "schedule": float(settings.outbox_poll_interval_seconds),
        },
        "delivery-maintenance": {"task": "app.jobs.maintain", "schedule": 60.0},
        "trash-cleanup": {
            "task": "app.jobs.cleanup_trash",
            "schedule": float(settings.trash_cleanup_interval_seconds),
        },
    },
)


@celery_app.task(name="app.jobs.deliver_reminder")
def deliver_reminder(delivery_id: str, claim_token: str) -> bool:
    return reminders.deliver(delivery_id, claim_token)


@celery_app.task(name="app.jobs.scan_due")
def scan_due() -> int:
    return reminders.scan_and_enqueue(deliver_reminder.delay)


@celery_app.task(name="app.jobs.publish_outbox")
def publish_outbox() -> int:
    return outbox.publish_outbox()


@celery_app.task(name="app.jobs.maintain")
def maintain() -> int:
    return maintenance.maintain()


@celery_app.task(name="app.jobs.cleanup_trash")
def cleanup_trash() -> int:
    return maintenance.cleanup_trash()
