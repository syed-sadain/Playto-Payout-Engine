from rest_framework import serializers
from .models import Merchant, BankAccount, LedgerEntry, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    masked_account = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_holder_name",
            "bank_name",
            "ifsc_code",
            "masked_account",
            "is_primary",
            "is_verified",
            "created_at",
        ]

    def get_masked_account(self, obj):
        return f"****{obj.account_number[-4:]}"


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()
    payout_id = serializers.UUIDField(source="payout_id", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount_paise",
            "amount_inr",
            "description",
            "reference_id",
            "payout_id",
            "created_at",
        ]

    def get_amount_inr(self, obj):
        # Display only — never use this for calculations
        return f"₹{obj.amount_paise / 100:.2f}"


class PayoutSerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()
    bank_account = BankAccountSerializer(read_only=True)
    bank_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "amount_paise",
            "amount_inr",
            "status",
            "bank_account",
            "bank_account_id",
            "attempt_count",
            "failure_reason",
            "processing_started_at",
            "completed_at",
            "failed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "attempt_count",
            "failure_reason",
            "processing_started_at",
            "completed_at",
            "failed_at",
            "created_at",
            "updated_at",
        ]

    def get_amount_inr(self, obj):
        return f"₹{obj.amount_paise / 100:.2f}"


class CreatePayoutSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=100)  # min ₹1
    bank_account_id = serializers.UUIDField()

    def validate_amount_paise(self, value):
        if value % 1 != 0:
            raise serializers.ValidationError("amount_paise must be a whole integer.")
        return value


class MerchantBalanceSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = ["id", "name", "email", "balance", "bank_accounts", "created_at"]

    def get_balance(self, obj):
        breakdown = obj.get_balance_breakdown()
        return {
            "available_paise": breakdown["available_paise"],
            "held_paise": breakdown["held_paise"],
            "ledger_balance_paise": breakdown["ledger_balance_paise"],
            "total_credits_paise": breakdown["total_credits_paise"],
            "total_debits_paise": breakdown["total_debits_paise"],
            # INR display strings
            "available_inr": f"₹{breakdown['available_paise'] / 100:.2f}",
            "held_inr": f"₹{breakdown['held_paise'] / 100:.2f}",
            "ledger_balance_inr": f"₹{breakdown['ledger_balance_paise'] / 100:.2f}",
        }


class MerchantListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "name", "email", "created_at"]
