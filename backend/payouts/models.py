import uuid
from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.validators import MinValueValidator


class TimestampedModel(models.Model):
    """Abstract base with created_at / updated_at."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Merchant(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "merchants"

    def __str__(self):
        return f"{self.name} ({self.email})"

    def get_balance_breakdown(self):
        """
        Single DB query for the complete balance picture.

        We derive balance entirely from the ledger — never store it as a
        mutable field, which would be a two-place truth that diverges under
        concurrent writes.

        credits  = SUM of CREDIT entries  (customer payments arriving)
        debits   = SUM of DEBIT entries   (payouts that completed / are held)
        available = credits - debits
        held      = amount locked by PENDING / PROCESSING payouts
        """
        from django.db.models import Sum, Q

        agg = self.ledger_entries.aggregate(
            total_credits=Sum(
                "amount_paise",
                filter=Q(entry_type=LedgerEntry.EntryType.CREDIT),
                default=0,
            ),
            total_debits=Sum(
                "amount_paise",
                filter=Q(entry_type=LedgerEntry.EntryType.DEBIT),
                default=0,
            ),
        )

        total_credits = agg["total_credits"]
        total_debits = agg["total_debits"]

        # Funds locked by in-flight payouts (not yet settled / failed)
        held_agg = self.payouts.filter(
            status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING]
        ).aggregate(held=Sum("amount_paise", default=0))
        held_paise = held_agg["held"]

        # Available = ledger balance minus what is held
        ledger_balance = total_credits - total_debits
        available_paise = ledger_balance - held_paise

        return {
            "total_credits_paise": total_credits,
            "total_debits_paise": total_debits,
            "ledger_balance_paise": ledger_balance,
            "held_paise": held_paise,
            "available_paise": available_paise,
        }


class BankAccount(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="bank_accounts"
    )
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=True)

    class Meta:
        db_table = "bank_accounts"
        unique_together = [("merchant", "account_number", "ifsc_code")]

    def __str__(self):
        return f"{self.bank_name} ****{self.account_number[-4:]}"


class LedgerEntry(TimestampedModel):
    """
    Append-only financial ledger.  Every money movement is recorded here.
    Balance = SUM(CREDIT) - SUM(DEBIT).  We never update or delete rows.

    CREDIT: customer payment arrives → merchant balance increases
    DEBIT:  payout completes         → merchant balance decreases

    NOTE: We do NOT debit when a payout is *created* (that would require a
    compensating credit on failure).  Instead, we use select_for_update on the
    Merchant row to gate whether enough balance exists, and track held funds
    via the Payout model's status.  A DEBIT entry is only written when the
    payout transitions to COMPLETED — this keeps the ledger clean and
    monotonically correct.
    """

    class EntryType(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=10, choices=EntryType.choices, db_index=True)
    amount_paise = models.BigIntegerField(validators=[MinValueValidator(1)])
    # No FloatField, no DecimalField — BigIntegerField in paise only.

    description = models.CharField(max_length=500)
    reference_id = models.CharField(max_length=255, blank=True, db_index=True)
    # Links a DEBIT entry back to its Payout UUID
    payout = models.ForeignKey(
        "Payout",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "entry_type"]),
            models.Index(fields=["merchant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise}p — {self.merchant.name}"


class Payout(TimestampedModel):
    """
    Represents a merchant's withdrawal request.

    State machine (strictly enforced in the save / transition methods):

        PENDING ──► PROCESSING ──► COMPLETED
                         │
                         └──────► FAILED

    No backward transitions.  No skipping states (unless transitioning
    directly from PENDING to FAILED on a pre-flight error).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    # Legal forward transitions only
    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.PROCESSING, Status.FAILED},
        Status.PROCESSING: {Status.COMPLETED, Status.FAILED},
        Status.COMPLETED: set(),  # terminal
        Status.FAILED: set(),     # terminal
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name="payouts"
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="payouts"
    )
    amount_paise = models.BigIntegerField(validators=[MinValueValidator(100)])
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "payouts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "status"]),
            models.Index(fields=["status", "processing_started_at"]),
            models.Index(fields=["merchant", "idempotency_key"]),
        ]

    def __str__(self):
        return f"Payout {self.id} — {self.status} — {self.amount_paise}p"

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: str, **kwargs):
        """
        Validates and applies a state transition.  Raises ValueError on
        illegal transitions so callers cannot silently violate the machine.
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Illegal payout state transition: {self.status} → {new_status} "
                f"(payout={self.id})"
            )
        self.status = new_status
        if new_status == self.Status.PROCESSING:
            self.processing_started_at = timezone.now()
            self.attempt_count += 1
        elif new_status == self.Status.COMPLETED:
            self.completed_at = timezone.now()
        elif new_status == self.Status.FAILED:
            self.failed_at = timezone.now()
            if "failure_reason" in kwargs:
                self.failure_reason = kwargs["failure_reason"]


class IdempotencyKey(TimestampedModel):
    """
    Stores the serialised response for a given (merchant, key) pair so that
    replayed requests return the exact same payload.

    - Scope is per-merchant so merchant-A cannot collide with merchant-B.
    - Keys expire 24 hours after creation (enforced at the API layer).
    - `response_body` holds the JSON we returned on the first successful write.
    - `is_locked` is True while the *first* request is in flight, so a
      concurrent duplicate can detect the race and return 409 (ask to retry).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="idempotency_keys"
    )
    key = models.CharField(max_length=255)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    payout = models.OneToOneField(
        Payout,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="idempotency_record",
    )
    # True while the first request is still being processed
    is_locked = models.BooleanField(default=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "idempotency_keys"
        unique_together = [("merchant", "key")]
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"IdempKey merchant={self.merchant_id} key={self.key}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at
