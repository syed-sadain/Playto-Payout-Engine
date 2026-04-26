"""
payouts/tests.py

Critical tests focused on concurrency correctness and idempotency.
These are the tests that catch the bugs that matter in production.
"""

import threading
import uuid
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import BankAccount, LedgerEntry, Merchant, Payout, IdempotencyKey
from .services import create_payout, InsufficientBalanceError


def make_merchant(name="Test Merchant", email=None):
    email = email or f"test-{uuid.uuid4()}@test.com"
    return Merchant.objects.create(name=name, email=email)


def make_bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant,
        account_number=str(uuid.uuid4().int)[:16],
        ifsc_code="HDFC0001234",
        account_holder_name=merchant.name,
        bank_name="HDFC Bank",
        is_primary=True,
        is_verified=True,
    )


def add_credits(merchant, amount_paise, description="Test credit"):
    return LedgerEntry.objects.create(
        merchant=merchant,
        entry_type=LedgerEntry.EntryType.CREDIT,
        amount_paise=amount_paise,
        description=description,
        reference_id=f"TEST-{uuid.uuid4()}",
    )


# ─── CONCURRENCY TEST ──────────────────────────────────────────────────────────


class ConcurrentPayoutTest(TransactionTestCase):
    """
    TransactionTestCase (not TestCase) because we need real transactions
    to commit so that concurrent threads can see each other's work.
    TestCase wraps everything in one transaction which blocks true concurrency.
    """

    def setUp(self):
        self.merchant = make_merchant("Concurrent Corp")
        self.bank_account = make_bank_account(self.merchant)
        # 100 rupees = 10,000 paise
        add_credits(self.merchant, 10_000, "Initial balance")

    def test_two_concurrent_60_rupee_payouts_exactly_one_succeeds(self):
        """
        Merchant has ₹100. Two simultaneous ₹60 payout requests.
        Exactly one should succeed; the other must raise InsufficientBalanceError.

        This is the canonical race condition test.
        """
        results = []
        errors = []
        lock = threading.Lock()

        def attempt_payout(key_suffix):
            try:
                payout = create_payout(
                    merchant=self.merchant,
                    amount_paise=6_000,  # ₹60
                    bank_account_id=self.bank_account.id,
                    idempotency_key=f"test-concurrent-{key_suffix}",
                )
                with lock:
                    results.append(payout)
            except InsufficientBalanceError as e:
                with lock:
                    errors.append(str(e))
            except Exception as e:
                with lock:
                    errors.append(f"UNEXPECTED: {e}")

        t1 = threading.Thread(target=attempt_payout, args=("key-1",))
        t2 = threading.Thread(target=attempt_payout, args=("key-2",))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one success, one failure
        self.assertEqual(len(results), 1, f"Expected 1 success, got {len(results)}: {results}")
        self.assertEqual(len(errors), 1, f"Expected 1 failure, got {len(errors)}: {errors}")

        # Verify held balance
        breakdown = self.merchant.get_balance_breakdown()
        self.assertEqual(breakdown["held_paise"], 6_000)
        self.assertEqual(breakdown["available_paise"], 4_000)  # ₹100 - ₹60 held

    def test_balance_invariant_holds_after_concurrent_payouts(self):
        """
        After multiple concurrent requests, the ledger invariant must hold:
        sum(CREDIT) - sum(DEBIT) == ledger_balance
        And ledger_balance - held == available
        """
        # Add more money
        add_credits(self.merchant, 50_000, "Extra credit")  # ₹600 total now

        results = []
        errors = []
        lock = threading.Lock()

        def attempt(amount, key):
            try:
                p = create_payout(
                    merchant=self.merchant,
                    amount_paise=amount,
                    bank_account_id=self.bank_account.id,
                    idempotency_key=key,
                )
                with lock:
                    results.append(p)
            except InsufficientBalanceError:
                with lock:
                    errors.append("insufficient")

        threads = [
            threading.Thread(target=attempt, args=(15_000, f"inv-test-{i}"))
            for i in range(5)  # 5 × ₹150 = ₹750 total requested vs ₹600 available
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify invariant
        bd = self.merchant.get_balance_breakdown()
        total_held = sum(p.amount_paise for p in results)
        self.assertEqual(bd["held_paise"], total_held)
        self.assertGreaterEqual(bd["available_paise"], 0, "Available must never go negative")

        # Core invariant: credits - debits == ledger_balance
        self.assertEqual(
            bd["total_credits_paise"] - bd["total_debits_paise"],
            bd["ledger_balance_paise"],
        )


# ─── IDEMPOTENCY TEST ─────────────────────────────────────────────────────────


class IdempotencyTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant("Idempotent Inc")
        self.bank_account = make_bank_account(self.merchant)
        add_credits(self.merchant, 100_000, "Seed credit")  # ₹1000

    def _post_payout(self, key, amount_paise=10_000):
        return self.client.post(
            f"/api/v1/merchants/{self.merchant.pk}/payouts/",
            data={"amount_paise": amount_paise, "bank_account_id": str(self.bank_account.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    @patch("payouts.views.process_payout_task")
    def test_same_idempotency_key_returns_identical_response(self, mock_task):
        """Second call with the same key returns the exact same response — no new payout."""
        mock_task.apply_async.return_value.id = str(uuid.uuid4())

        key = str(uuid.uuid4())

        r1 = self._post_payout(key)
        self.assertEqual(r1.status_code, 201)

        r2 = self._post_payout(key)
        self.assertEqual(r2.status_code, 201)

        # Same response body
        self.assertEqual(r1.json()["id"], r2.json()["id"])

        # Only one payout created
        payouts = Payout.objects.filter(merchant=self.merchant)
        self.assertEqual(payouts.count(), 1)

        # Task only fired once
        self.assertEqual(mock_task.apply_async.call_count, 1)

    @patch("payouts.views.process_payout_task")
    def test_different_keys_create_different_payouts(self, mock_task):
        """Each unique key creates a new payout."""
        mock_task.apply_async.return_value.id = str(uuid.uuid4())

        for i in range(3):
            r = self._post_payout(str(uuid.uuid4()), amount_paise=5_000)
            self.assertEqual(r.status_code, 201)

        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 3)

    @patch("payouts.views.process_payout_task")
    def test_idempotency_key_scoped_per_merchant(self, mock_task):
        """Same key used by two merchants creates two separate payouts."""
        mock_task.apply_async.return_value.id = str(uuid.uuid4())

        merchant2 = make_merchant("Other Merchant", "other@test.com")
        bank2 = make_bank_account(merchant2)
        add_credits(merchant2, 100_000, "Seed")

        shared_key = str(uuid.uuid4())

        r1 = self._post_payout(shared_key)
        self.assertEqual(r1.status_code, 201)

        r2 = self.client.post(
            f"/api/v1/merchants/{merchant2.pk}/payouts/",
            data={"amount_paise": 10_000, "bank_account_id": str(bank2.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=shared_key,
        )
        self.assertEqual(r2.status_code, 201)

        # Two different payouts
        self.assertNotEqual(r1.json()["id"], r2.json()["id"])

    def test_missing_idempotency_key_returns_400(self):
        r = self.client.post(
            f"/api/v1/merchants/{self.merchant.pk}/payouts/",
            data={"amount_paise": 10_000, "bank_account_id": str(self.bank_account.pk)},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Idempotency-Key", r.json()["error"])

    def test_expired_idempotency_key_treated_as_new(self):
        """An expired key does not replay; it starts a fresh payout."""
        from datetime import timedelta

        key = str(uuid.uuid4())
        # Create an already-expired IdempotencyKey record
        IdempotencyKey.objects.create(
            merchant=self.merchant,
            key=key,
            response_status=201,
            response_body={"id": str(uuid.uuid4()), "status": "PENDING"},
            is_locked=False,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        with patch("payouts.views.process_payout_task") as mock_task:
            mock_task.apply_async.return_value.id = str(uuid.uuid4())
            r = self._post_payout(key)
            # Should proceed as new request
            self.assertEqual(r.status_code, 201)
            mock_task.apply_async.assert_called_once()


# ─── STATE MACHINE TEST ───────────────────────────────────────────────────────


class StateMachineTest(TestCase):
    def setUp(self):
        self.merchant = make_merchant("State Corp")
        self.bank = make_bank_account(self.merchant)
        add_credits(self.merchant, 50_000, "Credit")
        self.payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank,
            amount_paise=10_000,
            status=Payout.Status.PENDING,
            idempotency_key=str(uuid.uuid4()),
        )

    def test_completed_to_pending_is_illegal(self):
        self.payout.status = Payout.Status.COMPLETED
        self.assertFalse(self.payout.can_transition_to(Payout.Status.PENDING))
        with self.assertRaises(ValueError):
            self.payout.transition_to(Payout.Status.PENDING)

    def test_failed_to_completed_is_illegal(self):
        self.payout.status = Payout.Status.FAILED
        self.assertFalse(self.payout.can_transition_to(Payout.Status.COMPLETED))
        with self.assertRaises(ValueError):
            self.payout.transition_to(Payout.Status.COMPLETED)

    def test_pending_to_processing_is_legal(self):
        self.payout.transition_to(Payout.Status.PROCESSING)
        self.assertEqual(self.payout.status, Payout.Status.PROCESSING)
        self.assertIsNotNone(self.payout.processing_started_at)
        self.assertEqual(self.payout.attempt_count, 1)

    def test_processing_to_completed_is_legal(self):
        self.payout.transition_to(Payout.Status.PROCESSING)
        self.payout.transition_to(Payout.Status.COMPLETED)
        self.assertEqual(self.payout.status, Payout.Status.COMPLETED)
        self.assertIsNotNone(self.payout.completed_at)

    def test_processing_to_failed_is_legal(self):
        self.payout.transition_to(Payout.Status.PROCESSING)
        self.payout.transition_to(Payout.Status.FAILED, failure_reason="Bank error")
        self.assertEqual(self.payout.status, Payout.Status.FAILED)
        self.assertEqual(self.payout.failure_reason, "Bank error")


# ─── LEDGER INTEGRITY TEST ────────────────────────────────────────────────────


class LedgerIntegrityTest(TestCase):
    def setUp(self):
        self.merchant = make_merchant("Ledger Corp")
        self.bank = make_bank_account(self.merchant)

    def test_balance_is_zero_with_no_entries(self):
        bd = self.merchant.get_balance_breakdown()
        self.assertEqual(bd["available_paise"], 0)
        self.assertEqual(bd["ledger_balance_paise"], 0)

    def test_balance_reflects_credits(self):
        add_credits(self.merchant, 50_000)
        add_credits(self.merchant, 30_000)
        bd = self.merchant.get_balance_breakdown()
        self.assertEqual(bd["total_credits_paise"], 80_000)
        self.assertEqual(bd["available_paise"], 80_000)

    def test_completed_payout_reduces_balance_via_debit(self):
        add_credits(self.merchant, 50_000)
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank,
            amount_paise=20_000,
            status=Payout.Status.COMPLETED,
            idempotency_key=str(uuid.uuid4()),
        )
        # Write debit as service would
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount_paise=20_000,
            description="Payout",
            payout=payout,
        )
        bd = self.merchant.get_balance_breakdown()
        self.assertEqual(bd["total_credits_paise"], 50_000)
        self.assertEqual(bd["total_debits_paise"], 20_000)
        self.assertEqual(bd["ledger_balance_paise"], 30_000)

    def test_no_float_fields_in_models(self):
        """Enforce that no FloatField is used anywhere in money-critical models."""
        from django.db.models import FloatField
        money_models = [Merchant, BankAccount, LedgerEntry, Payout]
        for model in money_models:
            for field in model._meta.get_fields():
                self.assertNotIsInstance(
                    field,
                    FloatField,
                    f"FloatField found on {model.__name__}.{getattr(field, 'name', '?')} — "
                    "use BigIntegerField in paise only.",
                )
