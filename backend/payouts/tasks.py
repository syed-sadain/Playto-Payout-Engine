"""
payouts/tasks.py

Celery tasks for background payout processing and maintenance.
"""

import logging
import uuid

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    reject_on_worker_lost=True,
    name="payouts.tasks.process_payout_task",
)
def process_payout_task(self, payout_id: str):
    """
    Main payout processing task.

    Picks up a PENDING payout and runs it through the bank simulation.
    Celery's own retry mechanism is a safety net, but primary retry logic
    lives in retry_stale_payouts_task (the sweeper) to handle hangs.
    """
    from .services import process_payout
    from .models import Payout

    logger.info(f"[task] Processing payout {payout_id}")

    try:
        payout = process_payout(uuid.UUID(payout_id))
        logger.info(f"[task] Payout {payout_id} finished with status: {payout.status}")
    except Payout.DoesNotExist:
        logger.error(f"[task] Payout {payout_id} not found — dropping task.")
    except Exception as exc:
        logger.exception(f"[task] Unexpected error processing payout {payout_id}: {exc}")
        # Exponential backoff: 5s, 25s, 125s
        raise self.retry(exc=exc, countdown=5 ** (self.request.retries + 1))


@shared_task(
    name="payouts.tasks.retry_stale_payouts_task",
    acks_late=True,
)
def retry_stale_payouts_task():
    """
    Sweeper task: runs every 30 seconds via Celery Beat.
    Finds PROCESSING payouts that have been stuck and either retries or fails them.
    """
    from .services import retry_stale_payouts

    logger.info("[sweeper] Checking for stale payouts...")
    try:
        retry_stale_payouts()
    except Exception as exc:
        logger.exception(f"[sweeper] Error during stale payout check: {exc}")


@shared_task(name="payouts.tasks.cleanup_expired_idempotency_keys")
def cleanup_expired_idempotency_keys():
    """
    Runs hourly. Deletes expired idempotency keys to keep the table lean.
    """
    from .models import IdempotencyKey

    now = timezone.now()
    deleted_count, _ = IdempotencyKey.objects.filter(expires_at__lt=now).delete()
    logger.info(f"[cleanup] Deleted {deleted_count} expired idempotency keys.")
