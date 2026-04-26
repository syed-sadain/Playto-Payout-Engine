"""
management/commands/seed_data.py

Populates the database with 3 merchants, bank accounts, and credit history.
Run with: python manage.py seed_data
"""

import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from payouts.models import BankAccount, LedgerEntry, Merchant


MERCHANTS = [
    {
        "name": "Arjun Sharma Designs",
        "email": "arjun@arjundesigns.in",
        "bank": {
            "account_number": "9876543210001",
            "ifsc_code": "HDFC0001234",
            "account_holder_name": "Arjun Sharma",
            "bank_name": "HDFC Bank",
            "is_primary": True,
        },
    },
    {
        "name": "PixelForge Studio",
        "email": "hello@pixelforge.in",
        "bank": {
            "account_number": "1234567890002",
            "ifsc_code": "ICIC0005678",
            "account_holder_name": "PixelForge Studio LLP",
            "bank_name": "ICICI Bank",
            "is_primary": True,
        },
    },
    {
        "name": "Meera Krishnan Consulting",
        "email": "meera@mkconsult.in",
        "bank": {
            "account_number": "5555666677778",
            "ifsc_code": "SBIN0001111",
            "account_holder_name": "Meera Krishnan",
            "bank_name": "State Bank of India",
            "is_primary": True,
        },
    },
]

# Simulated inbound customer payment credits per merchant (amount in paise)
CREDIT_HISTORY = [
    # Arjun: Logo design projects
    [
        (75_000_00, "USD payment from Acme Corp — Invoice #1001"),
        (120_000_00, "USD payment from TechStartup Inc — Invoice #1002"),
        (45_000_00, "USD payment from GlobalMedia — Invoice #1003"),
        (90_000_00, "USD payment from NordVentures — Invoice #1004"),
    ],
    # PixelForge: Web design projects
    [
        (200_000_00, "USD payment from FinanceApp LLC — Invoice #2001"),
        (150_000_00, "USD payment from RetailChain Co — Invoice #2002"),
        (80_000_00, "USD payment from SaaS Platform — Invoice #2003"),
    ],
    # Meera: Consulting retainers
    [
        (300_000_00, "USD payment from MNC Corp — Retainer Jan"),
        (300_000_00, "USD payment from MNC Corp — Retainer Feb"),
        (150_000_00, "USD payment from StartupXYZ — Strategy session"),
        (200_000_00, "USD payment from PE Fund — Due diligence"),
    ],
]


class Command(BaseCommand):
    help = "Seed database with merchants, bank accounts, and credit history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            LedgerEntry.objects.all().delete()
            BankAccount.objects.all().delete()
            Merchant.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Cleared."))

        with transaction.atomic():
            for idx, (merchant_data, credits) in enumerate(
                zip(MERCHANTS, CREDIT_HISTORY)
            ):
                merchant, created = Merchant.objects.get_or_create(
                    email=merchant_data["email"],
                    defaults={"name": merchant_data["name"]},
                )
                action = "Created" if created else "Found existing"
                self.stdout.write(f"{action} merchant: {merchant.name}")

                bank_data = merchant_data["bank"]
                bank_account, _ = BankAccount.objects.get_or_create(
                    merchant=merchant,
                    account_number=bank_data["account_number"],
                    ifsc_code=bank_data["ifsc_code"],
                    defaults={
                        "account_holder_name": bank_data["account_holder_name"],
                        "bank_name": bank_data["bank_name"],
                        "is_primary": bank_data["is_primary"],
                        "is_verified": True,
                    },
                )
                self.stdout.write(f"  Bank: {bank_account.bank_name} ****{bank_account.account_number[-4:]}")

                # Seed credits if none exist
                if not LedgerEntry.objects.filter(merchant=merchant).exists():
                    for amount_paise, description in credits:
                        LedgerEntry.objects.create(
                            merchant=merchant,
                            entry_type=LedgerEntry.EntryType.CREDIT,
                            amount_paise=amount_paise,
                            description=description,
                            reference_id=f"SIM-PAY-{idx}-{random.randint(10000,99999)}",
                        )
                    total_credits = sum(a for a, _ in credits)
                    self.stdout.write(
                        f"  Seeded {len(credits)} credits totalling "
                        f"₹{total_credits / 100:,.2f}"
                    )

        self.stdout.write(self.style.SUCCESS("\n✓ Seed complete. Merchants:"))
        for m in Merchant.objects.all():
            breakdown = m.get_balance_breakdown()
            self.stdout.write(
                f"  {m.name} | available ₹{breakdown['available_paise'] / 100:,.2f} | "
                f"id={m.id}"
            )
