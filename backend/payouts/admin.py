from django.contrib import admin
from .models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "is_active", "created_at"]
    search_fields = ["name", "email"]
    list_filter = ["is_active"]


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["merchant", "bank_name", "account_number", "ifsc_code", "is_primary", "is_verified"]
    search_fields = ["merchant__name", "bank_name", "account_number"]
    list_filter = ["bank_name", "is_verified", "is_primary"]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["merchant", "entry_type", "amount_paise", "description", "created_at"]
    search_fields = ["merchant__name", "description", "reference_id"]
    list_filter = ["entry_type"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["id", "merchant", "amount_paise", "status", "attempt_count", "created_at"]
    search_fields = ["merchant__name", "id"]
    list_filter = ["status"]
    readonly_fields = ["id", "created_at", "updated_at", "celery_task_id"]


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ["merchant", "key", "is_locked", "response_status", "expires_at", "created_at"]
    search_fields = ["merchant__name", "key"]
    list_filter = ["is_locked"]
    readonly_fields = ["id", "created_at", "updated_at"]