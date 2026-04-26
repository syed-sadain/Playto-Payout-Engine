"""
payouts/views.py — API views (thin layer, delegates to services)
"""

import logging
import uuid

from django.db import IntegrityError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .models import IdempotencyKey, LedgerEntry, Merchant, Payout
from .serializers import (
    CreatePayoutSerializer,
    LedgerEntrySerializer,
    MerchantBalanceSerializer,
    MerchantListSerializer,
    PayoutSerializer,
)
from .services import (
    InsufficientBalanceError,
    InvalidBankAccountError,
    create_payout,
    get_or_create_idempotency_key,
)
from .tasks import process_payout_task

logger = logging.getLogger(__name__)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _resolve_merchant(merchant_id):
    try:
        return Merchant.objects.get(pk=merchant_id, is_active=True), None
    except Merchant.DoesNotExist:
        return None, Response({"error": "Merchant not found."}, status=status.HTTP_404_NOT_FOUND)


def _handle_payout_create(request: Request, merchant: Merchant) -> Response:
    """Shared logic for both nested and flat payout creation endpoints."""
    raw_key = request.headers.get("Idempotency-Key", "").strip()
    if not raw_key:
        return Response(
            {"error": "Idempotency-Key header is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        uuid.UUID(raw_key)
    except ValueError:
        return Response(
            {"error": "Idempotency-Key must be a valid UUID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Idempotency gate ──────────────────────────────────────────────────
    try:
        idem_key, created = get_or_create_idempotency_key(merchant, raw_key)
    except IntegrityError:
        try:
            idem_key = IdempotencyKey.objects.get(merchant=merchant, key=raw_key)
            created = False
        except IdempotencyKey.DoesNotExist:
            return Response(
                {"error": "Idempotency conflict — please retry."},
                status=status.HTTP_409_CONFLICT,
            )

    if not created:
        if idem_key.is_expired:
            idem_key.delete()
            idem_key, created = get_or_create_idempotency_key(merchant, raw_key)
        elif idem_key.is_locked:
            return Response(
                {"error": "Request with this key is already in flight. Retry shortly."},
                status=status.HTTP_409_CONFLICT,
            )
        else:
            logger.info("Idempotency replay: key=%s merchant=%s", raw_key, merchant.pk)
            return Response(idem_key.response_body, status=idem_key.response_status)

    # ── Validate body ─────────────────────────────────────────────────────
    serializer = CreatePayoutSerializer(data=request.data)
    if not serializer.is_valid():
        idem_key.delete()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Create payout (atomic, with row-level lock) ───────────────────────
    try:
        payout = create_payout(
            merchant=merchant,
            amount_paise=serializer.validated_data["amount_paise"],
            bank_account_id=serializer.validated_data["bank_account_id"],
            idempotency_key=raw_key,
        )
    except InsufficientBalanceError as exc:
        idem_key.delete()
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except InvalidBankAccountError as exc:
        idem_key.delete()
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.exception("Unexpected error creating payout: %s", exc)
        idem_key.delete()
        return Response({"error": "Internal error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ── Enqueue background processing ────────────────────────────────────
    task = process_payout_task.apply_async(args=[str(payout.id)], countdown=1)
    payout.celery_task_id = task.id
    payout.save(update_fields=["celery_task_id"])

    # ── Store response for idempotency replay ────────────────────────────
    response_data = PayoutSerializer(payout).data
    resp_status = status.HTTP_201_CREATED
    idem_key.response_body = response_data
    idem_key.response_status = resp_status
    idem_key.payout = payout
    idem_key.is_locked = False
    idem_key.save(update_fields=["response_body", "response_status", "payout", "is_locked"])

    return Response(response_data, status=resp_status)


# ─── Merchant endpoints ───────────────────────────────────────────────────────

@api_view(["GET"])
def list_merchants(request: Request) -> Response:
    merchants = Merchant.objects.filter(is_active=True).prefetch_related("bank_accounts")
    return Response(MerchantListSerializer(merchants, many=True).data)


@api_view(["GET"])
def merchant_detail(request: Request, merchant_id) -> Response:
    merchant, err = _resolve_merchant(merchant_id)
    if err:
        return err
    return Response(MerchantBalanceSerializer(merchant).data)


@api_view(["GET"])
def merchant_ledger(request: Request, merchant_id) -> Response:
    merchant, err = _resolve_merchant(merchant_id)
    if err:
        return err
    entries = (
        LedgerEntry.objects.filter(merchant=merchant)
        .select_related("payout")
        .order_by("-created_at")[:100]
    )
    return Response({"results": LedgerEntrySerializer(entries, many=True).data})


# ─── Payout endpoints ─────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
def merchant_payouts(request: Request, merchant_id) -> Response:
    merchant, err = _resolve_merchant(merchant_id)
    if err:
        return err

    if request.method == "POST":
        return _handle_payout_create(request, merchant)

    # GET — list
    payouts = (
        Payout.objects.filter(merchant=merchant)
        .select_related("bank_account")
        .order_by("-created_at")[:50]
    )
    return Response({"results": PayoutSerializer(payouts, many=True).data})


@api_view(["GET"])
def payout_detail(request: Request, merchant_id, payout_id) -> Response:
    try:
        payout = Payout.objects.select_related("bank_account", "merchant").get(
            pk=payout_id, merchant_id=merchant_id
        )
    except Payout.DoesNotExist:
        return Response({"error": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(PayoutSerializer(payout).data)


@api_view(["POST"])
def payouts_flat(request: Request) -> Response:
    """
    POST /api/v1/payouts
    Merchant identified via X-Merchant-Id header (spec convenience endpoint).
    """
    merchant_id_raw = request.headers.get("X-Merchant-Id", "").strip()
    if not merchant_id_raw:
        return Response(
            {"error": "X-Merchant-Id header is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        merchant_id = uuid.UUID(merchant_id_raw)
    except ValueError:
        return Response({"error": "X-Merchant-Id must be a valid UUID."}, status=status.HTTP_400_BAD_REQUEST)

    merchant, err = _resolve_merchant(merchant_id)
    if err:
        return err
    return _handle_payout_create(request, merchant)
