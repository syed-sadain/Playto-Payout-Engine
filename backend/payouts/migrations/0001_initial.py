from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Merchant",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"db_table": "merchants"},
        ),
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account_number", models.CharField(max_length=20)),
                ("ifsc_code", models.CharField(max_length=11)),
                ("account_holder_name", models.CharField(max_length=255)),
                ("bank_name", models.CharField(max_length=255)),
                ("is_primary", models.BooleanField(default=False)),
                ("is_verified", models.BooleanField(default=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_accounts", to="payouts.merchant")),
            ],
            options={"db_table": "bank_accounts"},
        ),
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount_paise", models.BigIntegerField(validators=[django.core.validators.MinValueValidator(100)])),
                ("status", models.CharField(
                    choices=[("PENDING","Pending"),("PROCESSING","Processing"),("COMPLETED","Completed"),("FAILED","Failed")],
                    db_index=True, default="PENDING", max_length=20,
                )),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("failure_reason", models.TextField(blank=True)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("idempotency_key", models.CharField(db_index=True, max_length=255)),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payouts", to="payouts.merchant")),
                ("bank_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payouts", to="payouts.bankaccount")),
            ],
            options={"db_table": "payouts", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("entry_type", models.CharField(
                    choices=[("CREDIT","Credit"),("DEBIT","Debit")],
                    db_index=True, max_length=10,
                )),
                ("amount_paise", models.BigIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("description", models.CharField(max_length=500)),
                ("reference_id", models.CharField(blank=True, db_index=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="payouts.merchant")),
                ("payout", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="payouts.payout")),
            ],
            options={"db_table": "ledger_entries", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="IdempotencyKey",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=255)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("is_locked", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="idempotency_keys", to="payouts.merchant")),
                ("payout", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="idempotency_record", to="payouts.payout")),
            ],
            options={"db_table": "idempotency_keys"},
        ),
        # Unique constraints
        migrations.AlterUniqueTogether(
            name="bankaccount",
            unique_together={("merchant", "account_number", "ifsc_code")},
        ),
        migrations.AlterUniqueTogether(
            name="idempotencykey",
            unique_together={("merchant", "key")},
        ),
        # Indexes
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["merchant", "status"], name="payouts_merchant_status_idx"),
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["status", "processing_started_at"], name="payouts_status_processing_idx"),
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["merchant", "idempotency_key"], name="payouts_merchant_idem_idx"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["merchant", "entry_type"], name="ledger_merchant_type_idx"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["merchant", "created_at"], name="ledger_merchant_date_idx"),
        ),
        migrations.AddIndex(
            model_name="idempotencykey",
            index=models.Index(fields=["expires_at"], name="idem_expires_idx"),
        ),
    ]
