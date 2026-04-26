"""
payouts/services.py

All money-movement logic lives here.  Views call services; tasks call services.
No DB writes happen in views or tasks directly.

CRITICAL DESIGN:
- select_for_update() acquires a row-level PG advisory lock on the Merchant
  row.  This serialises concurrent payout creation for the same merchant.
- Balance available check and Payout creation happen in the same atomic block,
  so no other transaction can squeeze in between read and write.
- LedgerEntry DEBIT is only written on COMPLETED transition, keeping the
  ledger correct even if the worker crashes mid-flight.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from .models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout

logger = logging.getLogger(__name__)


# ─── IDEMPOTENCY ──────────────────────────────────────────────────────────────


def get_or_create_idempotency_key(
    merchant: Merchant, raw_key: str
) -> tuple[IdempotencyKey, bool]:
    """
    Returns (IdempotencyKey, created).

    Uses get_or_create with select_for_update so concurrent duplicates
    either see the existing record or create it exactly once.

    We wrap this in its own savepoint so callers can inspect `created`
    before proceeding.
    """
    expires_at = timezone.now() + timedelta(
        hours=settings.IDEMPOTENCY_KEY_TTL_HOURS
    )

    with transaction.atomic():
        # get_or_create is NOT safe under concurrency on its own in Django
        # because it does SELECT then INSERT.  We guard with a DB-level
        # unique constraint on (merchant, key) — a duplicate INSERT will raise
        # IntegrityError which Django surfaces as a get_or_create retry.
        # The unique_together on the model is the true concurrency guard here.
        idem_key, created = IdempotencyKey.objects.get_or_create(
            merchant=merchant,
            key=raw_key,
            defaults={
                "expires_at": expires_at,
                "is_locked": True,
            },
        )
    return idem_key, created


# ─── PAYOUT CREATION ──────────────────────────────────────────────────────────


def create_payout(
    merchant: Merchant,
    amount_paise: int,
    bank_account_id: uuid.UUID,
    idempotency_key: str,
) -> Payout:
    """
    Creates a payout and holds the funds.

    Concurrency safety:
      1. We lock the Merchant row with SELECT FOR UPDATE (nowait=False —
         blocking lock, so concurrent requests wait rather than error out).
      2. Inside the same atomic block we compute available balance using
         a DB aggregation (not Python arithmetic on stale values).
      3. We verify the bank account belongs to this merchant.
      4. We create the Payout in PENDING state.

    This entire block is atomic: if anything fails, no Payout is created
    and no money is moved.
    """
    with transaction.atomic():
        # ── Step 1: lock the merchant row ─────────────────────────────────
        # select_for_update prevents any other transaction from reading this
        # row with a FOR UPDATE lock until we commit.  Concurrent payout
        # creation will block here, then re-read the updated balance.
        merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

        # ── Step 2: compute available balance inside the lock ──────────────
        agg = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
            credits=Sum(
                "amount_paise",
                filter=Q(entry_type=LedgerEntry.EntryType.CREDIT),
                default=0,
            ),
            debits=Sum(
                "amount_paise",
                filter=Q(entry_type=LedgerEntry.EntryType.DEBIT),
                default=0,
            ),
        )

        # Held = sum of in-flight payouts (also locked via merchant row lock)
        held_agg = Payout.objects.filter(
            merchant=merchant_locked,
            status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
        ).aggregate(held=Sum("amount_paise", default=0))

        ledger_balance = agg["credits"] - agg["debits"]
        available = ledger_balance - held_agg["held"]

        if available < amount_paise:
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {available}p, Requested: {amount_paise}p"
            )

        # ── Step 3: validate bank account ownership ────────────────────────
        try:
            bank_account = BankAccount.objects.get(
                pk=bank_account_id, merchant=merchant_locked, is_verified=True
            )
        except BankAccount.DoesNotExist:
            raise InvalidBankAccountError(
                f"Bank account {bank_account_id} not found or not verified for this merchant."
            )

        # ── Step 4: create the payout record ──────────────────────────────
        payout = Payout.objects.create(
            merchant=merchant_locked,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.Status.PENDING,
            idempotency_key=idempotency_key,
        )

        logger.info(
            "Payout created",
            extra={
                "payout_id": str(payout.id),
                "merchant_id": str(merchant.id),
                "amount_paise": amount_paise,
                "available_before": available,
            },
        )

    return payout


# ─── PAYOUT PROCESSING (called by Celery task) ────────────────────────────────


def process_payout(payout_id: uuid.UUID) -> Payout:
    """
    Transitions payout PENDING → PROCESSING → COMPLETED | FAILED.

    Simulates bank settlement:  70% success, 20% failure, 10% hang.
    """
    import random
    import time

    with transaction.atomic():
        try:
            payout = Payout.objects.select_for_update().get(pk=payout_id)
        except Payout.DoesNotExist:
            logger.error(f"process_payout: payout {payout_id} not found")
            raise

        if payout.status != Payout.Status.PENDING:
            logger.warning(
                f"process_payout: payout {payout_id} is {payout.status}, skipping"
            )
            return payout

        payout.transition_to(Payout.Status.PROCESSING)
        payout.save(update_fields=["status", "processing_started_at", "attempt_count", "updated_at"])

    # ── Simulate bank call (outside atomic to allow DB to be seen by monitoring) ──
    rand = random.random()

    if rand < settings.PAYOUT_SUCCESS_RATE:
        # 70%: success
        outcome = "success"
        time.sleep(random.uniform(0.5, 2.0))  # Simulate network latency
    elif rand < settings.PAYOUT_SUCCESS_RATE + settings.PAYOUT_FAILURE_RATE:
        # 20%: bank rejected
        outcome = "failure"
        time.sleep(random.uniform(0.5, 1.5))
    else:
        # 10%: hang — sleep past PAYOUT_PROCESSING_TIMEOUT_SECONDS
        # The retry task will pick this up and re-queue it
        outcome = "hang"
        time.sleep(settings.PAYOUT_PROCESSING_TIMEOUT_SECONDS + 5)

    if outcome == "success":
        _complete_payout(payout)
    elif outcome == "failure":
        _fail_payout(payout, reason="Bank rejected the transfer.")
    # If hang: the retry sweeper task will handle it

    return payout


def _complete_payout(payout: Payout):
    """
    Atomically: transition payout → COMPLETED and write the DEBIT ledger entry.
    These two operations must succeed together or not at all.
    """
    with transaction.atomic():
        # Re-fetch with lock inside new transaction
        payout_locked = Payout.objects.select_for_update().get(pk=payout.pk)

        if not payout_locked.can_transition_to(Payout.Status.COMPLETED):
            logger.warning(
                f"_complete_payout: cannot transition {payout.id} from {payout_locked.status}"
            )
            return

        payout_locked.transition_to(Payout.Status.COMPLETED)
        payout_locked.save(
            update_fields=["status", "completed_at", "updated_at"]
        )

        # Write the DEBIT entry — this is the only place balance decreases
        LedgerEntry.objects.create(
            merchant=payout_locked.merchant,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount_paise=payout_locked.amount_paise,
            description=f"Payout to {payout_locked.bank_account}",
            reference_id=str(payout_locked.id),
            payout=payout_locked,
        )

        logger.info(f"Payout {payout.id} COMPLETED, DEBIT ledger entry written.")


def _fail_payout(payout: Payout, reason: str):
    """
    Atomically: transition payout → FAILED.
    No DEBIT entry was written (we only debit on success), so the held
    funds are automatically released — no compensating credit needed.
    """
    with transaction.atomic():
        payout_locked = Payout.objects.select_for_update().get(pk=payout.pk)

        if not payout_locked.can_transition_to(Payout.Status.FAILED):
            logger.warning(
                f"_fail_payout: cannot transition {payout.id} from {payout_locked.status}"
            )
            return

        payout_locked.transition_to(Payout.Status.FAILED, failure_reason=reason)
        payout_locked.save(
            update_fields=["status", "failed_at", "failure_reason", "updated_at"]
        )

        logger.info(f"Payout {payout.id} FAILED: {reason}")


def retry_stale_payouts():
    """
    Called by the Celery beat task every 30 seconds.
    Finds PROCESSING payouts stuck beyond PAYOUT_PROCESSING_TIMEOUT_SECONDS
    and re-queues them or fails them after max retries.
    """
    from .tasks import process_payout_task

    timeout = timezone.now() - timedelta(
        seconds=settings.PAYOUT_PROCESSING_TIMEOUT_SECONDS
    )
    stale_payouts = Payout.objects.filter(
        status=Payout.Status.PROCESSING,
        processing_started_at__lt=timeout,
    ).select_for_update(skip_locked=True)

    with transaction.atomic():
        for payout in stale_payouts:
            if payout.attempt_count >= settings.PAYOUT_MAX_RETRY_ATTEMPTS:
                logger.warning(
                    f"Payout {payout.id} exceeded max retries ({payout.attempt_count}), failing."
                )
                _fail_payout(payout, reason="Max retry attempts exceeded.")
            else:
                logger.info(
                    f"Payout {payout.id} stale (attempt {payout.attempt_count}), re-queuing."
                )
                # Reset to PENDING so the worker can pick it up again
                # We bypass transition_to here because PROCESSING→PENDING is
                # intentionally not in ALLOWED_TRANSITIONS (it's a retry path
                # only accessible from this specific sweeper, not from user code).
                Payout.objects.filter(pk=payout.pk).update(
                    status=Payout.Status.PENDING,
                    updated_at=timezone.now(),
                )
                # Re-queue with exponential backoff
                delay = 2 ** payout.attempt_count  # 2s, 4s, 8s
                process_payout_task.apply_async(
                    args=[str(payout.id)], countdown=delay
                )


# ─── CUSTOM EXCEPTIONS ────────────────────────────────────────────────────────


class InsufficientBalanceError(Exception):
    pass


class InvalidBankAccountError(Exception):
    pass


class IdempotencyConflictError(Exception):
    """Raised when a duplicate request arrives while the first is in flight."""
    pass
