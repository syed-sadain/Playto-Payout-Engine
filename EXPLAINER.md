# EXPLAINER.md

> Engineering decisions for the Playto Payout Engine.
> This document explains what I built, why, and where the hard parts live.

---

## 1. The Ledger

### Balance Calculation Query

```python
# payouts/services.py → create_payout()
# Also used in models.py → Merchant.get_balance_breakdown()

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

held_agg = Payout.objects.filter(
    merchant=merchant_locked,
    status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
).aggregate(held=Sum("amount_paise", default=0))

ledger_balance = agg["credits"] - agg["debits"]
available = ledger_balance - held_agg["held"]
```

This maps to a single SQL aggregation:

```sql
SELECT
    SUM(amount_paise) FILTER (WHERE entry_type = 'CREDIT') AS credits,
    SUM(amount_paise) FILTER (WHERE entry_type = 'DEBIT')  AS debits
FROM ledger_entries
WHERE merchant_id = $1;

SELECT COALESCE(SUM(amount_paise), 0) AS held
FROM payouts
WHERE merchant_id = $1 AND status IN ('PENDING', 'PROCESSING');
```

### Why this model?

**The ledger is append-only.** We never `UPDATE` or `DELETE` a `LedgerEntry`. Every money movement — credit in, debit out — is a new row. Balance is always derived by aggregation, never stored as a mutable column.

**Why no `balance` column on `Merchant`?**
A mutable balance field creates two sources of truth. Under concurrent writes you'd need to UPDATE the balance atomically with every ledger entry, and if any transaction partially fails, the balance diverges silently. The append-only ledger means the only invariant is "this table's rows are correct" — no sync problem, no drift.

**Why DEBIT only on COMPLETED, not on payout creation?**
Early designs I considered write a DEBIT when a payout is *created* and a compensating CREDIT when it fails. This works but pollutes the ledger with noise (every failure leaves a credit stub). Instead:

- On payout creation: no ledger write. We hold funds by tracking in-flight payout amounts separately.
- On COMPLETED: write exactly one DEBIT entry, atomically with the status transition.
- On FAILED: no ledger write needed. The held funds are released because we stop counting that payout in the `held` aggregation.

This keeps the ledger semantically clean: credits are customer payments, debits are completed payouts — nothing else.

**BigIntegerField in paise — no floats, no Decimal:**
`float` cannot represent 0.1 exactly in binary. `Decimal` is safer but adds complexity (scale, precision decisions, ORM overhead). We store everything as `BigIntegerField` in paise (integer). ₹1 = 100 paise. All arithmetic is integer arithmetic. Division to display INR strings happens only in serializers, only for display, and never feeds back into a calculation.

---

## 2. The Lock

### Exact code that prevents two concurrent payouts from overdrawing

```python
# payouts/services.py → create_payout()

with transaction.atomic():
    # 1. Acquire row-level lock on the Merchant row.
    #    Any other transaction trying to lock the SAME merchant will BLOCK here
    #    until this transaction commits or rolls back.
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

    # 2. Compute balance INSIDE the lock, so we read the state that includes
    #    any payouts committed by transactions that ran before us.
    agg = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
        credits=Sum("amount_paise", filter=Q(entry_type="CREDIT"), default=0),
        debits=Sum("amount_paise", filter=Q(entry_type="DEBIT"), default=0),
    )
    held_agg = Payout.objects.filter(
        merchant=merchant_locked,
        status__in=["PENDING", "PROCESSING"],
    ).aggregate(held=Sum("amount_paise", default=0))

    available = (agg["credits"] - agg["debits"]) - held_agg["held"]

    # 3. Check-then-act is safe because we hold the lock.
    #    No other transaction can create a Payout for this merchant until we commit.
    if available < amount_paise:
        raise InsufficientBalanceError(...)

    # 4. Create the Payout inside the same atomic block.
    payout = Payout.objects.create(merchant=merchant_locked, ...)
```

### Database primitive

**`SELECT FOR UPDATE`** — a row-level exclusive lock in PostgreSQL.

When transaction A executes `SELECT * FROM merchants WHERE id=$1 FOR UPDATE`, PostgreSQL places an exclusive lock on that row. Transaction B attempting the same `SELECT FOR UPDATE` on the same row will **block** (not fail) until transaction A commits or rolls back.

**Why this is correct:**

Consider the race without locking:
```
T1: SELECT available = 10000
T2: SELECT available = 10000   ← reads same value before T1 commits
T1: available (10000) >= 6000 → OK → INSERT payout (held: 6000)
T2: available (10000) >= 6000 → OK → INSERT payout (held: 6000) ← OVERDRAFT
```

With `SELECT FOR UPDATE`:
```
T1: SELECT ... FOR UPDATE  ← acquires lock
T2: SELECT ... FOR UPDATE  ← BLOCKS, waits for T1
T1: available (10000) >= 6000 → OK → INSERT payout → COMMIT (releases lock)
T2: resumes, re-reads available = 10000 - 6000 (held) = 4000
T2: 4000 < 6000 → InsufficientBalanceError → ROLLBACK
```

**Why not Python-level locking (threading.Lock)?**

Python locks are in-process only. Under Gunicorn with 4 workers (4 separate processes), a Python-level lock in one worker is invisible to the others. The database lock is the only primitive that works across all processes, connections, and servers.

**`skip_locked=True` in the sweeper:**

The retry sweeper uses `select_for_update(skip_locked=True)` to skip payouts already being processed by another worker, avoiding a pile-up of workers all trying to retry the same stale payout simultaneously.

---

## 3. The Idempotency

### How the system knows it has seen a key before

We persist idempotency keys in the `idempotency_keys` table with a `UNIQUE(merchant_id, key)` constraint. On every `POST /payouts`:

1. We attempt `get_or_create(merchant=m, key=raw_key)`.
2. If `created=True` → this is a new key. Proceed to create the payout.
3. If `created=False` → we have seen this key before. Return the stored `response_body` with the stored `response_status` without creating anything new.

The unique constraint is enforced at the database level — not in Python. This is important: two concurrent requests with the same key will race to `INSERT`. The database allows exactly one; the other gets an `IntegrityError`, which we catch and handle by fetching the winning row.

### Scoping

Keys are scoped per merchant via `UNIQUE(merchant_id, key)`. Merchant A using key `abc-123` and merchant B using key `abc-123` create two separate `IdempotencyKey` rows. They never collide.

### What happens when the first request is in-flight?

Every new `IdempotencyKey` is created with `is_locked=True`. The lock is only released (set to `is_locked=False`) **after** the payout is created and the response is stored.

```python
# After successful payout creation:
idem_key.response_body = response_data
idem_key.response_status = 201
idem_key.payout = payout
idem_key.is_locked = False      # ← unlock now that we have a response to replay
idem_key.save(...)
```

If a second request arrives while `is_locked=True`:

```python
elif idem_key.is_locked:
    return Response(
        {"error": "A request with this Idempotency-Key is already being processed. Retry shortly."},
        status=status.HTTP_409_CONFLICT,
    )
```

This is the standard pattern used by Stripe and Braintree. The client gets a `409` and knows to wait briefly and retry — the key is valid, just not yet settled.

### Key expiry

Keys have an `expires_at` timestamp (24 hours from creation). On every request we check:

```python
if idem_key.is_expired:
    idem_key.delete()
    # treat as new key → create fresh
```

A Celery beat task runs hourly to clean up expired keys from the database.

---

## 4. The State Machine

### Where failed→completed is blocked

The state machine is enforced in `Payout.ALLOWED_TRANSITIONS` and the `transition_to` method:

```python
# payouts/models.py

ALLOWED_TRANSITIONS = {
    Status.PENDING:    {Status.PROCESSING, Status.FAILED},
    Status.PROCESSING: {Status.COMPLETED, Status.FAILED},
    Status.COMPLETED:  set(),   # terminal — no transitions out
    Status.FAILED:     set(),   # terminal — no transitions out
}

def transition_to(self, new_status: str, **kwargs):
    if not self.can_transition_to(new_status):
        raise ValueError(
            f"Illegal payout state transition: {self.status} → {new_status} "
            f"(payout={self.id})"
        )
    # ... apply transition
```

`can_transition_to` is:
```python
def can_transition_to(self, new_status: str) -> bool:
    return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())
```

For a `FAILED` payout, `ALLOWED_TRANSITIONS[Status.FAILED]` is an empty set. `Status.COMPLETED not in set()` → `False` → `ValueError` raised. This check fires anywhere `transition_to` is called — in the service layer, in the worker task, always.

**No database-level enforcement of transitions?** We don't add a DB check constraint because the valid transitions depend on the current value and target value together, not just one column. The Python enforcement is authoritative; the `select_for_update()` around every transition ensures no race can bypass it.

### Atomic DEBIT + COMPLETED

```python
# payouts/services.py → _complete_payout()

with transaction.atomic():
    payout_locked = Payout.objects.select_for_update().get(pk=payout.pk)

    if not payout_locked.can_transition_to(Payout.Status.COMPLETED):
        return  # already transitioned by another worker — skip

    payout_locked.transition_to(Payout.Status.COMPLETED)
    payout_locked.save(update_fields=["status", "completed_at", "updated_at"])

    LedgerEntry.objects.create(   # ← DEBIT written atomically with status change
        merchant=payout_locked.merchant,
        entry_type=LedgerEntry.EntryType.DEBIT,
        amount_paise=payout_locked.amount_paise,
        payout=payout_locked,
        description=f"Payout to {payout_locked.bank_account}",
    )
```

If the process crashes between the `save()` and `LedgerEntry.create()`, the whole transaction rolls back — payout stays in `PROCESSING`, DEBIT is never written. The retry sweeper picks it up and tries again. This is exactly what we want.

---

## 5. The AI Audit

### What AI wrote that was subtly wrong

While generating the initial concurrency implementation, the AI produced this pattern:

```python
# ❌ WHAT AI GENERATED (wrong)
def create_payout(merchant, amount_paise, bank_account_id, idempotency_key):
    with transaction.atomic():
        # Fetch merchant (no lock)
        merchant_obj = Merchant.objects.get(pk=merchant.pk)
        
        # Compute balance in Python from fetched rows
        credits = sum(
            e.amount_paise 
            for e in merchant_obj.ledger_entries.filter(entry_type="CREDIT")
        )
        debits = sum(
            e.amount_paise 
            for e in merchant_obj.ledger_entries.filter(entry_type="DEBIT")
        )
        held = sum(
            p.amount_paise 
            for p in merchant_obj.payouts.filter(status__in=["PENDING", "PROCESSING"])
        )
        available = credits - debits - held
        
        if available < amount_paise:
            raise InsufficientBalanceError(...)
        
        payout = Payout.objects.create(...)
    return payout
```

**Two bugs I caught:**

**Bug 1: No row lock.** `Merchant.objects.get(pk=...)` without `select_for_update()` is a plain `SELECT`. Even inside `transaction.atomic()`, two concurrent transactions can both run this SELECT simultaneously — they see the same merchant row, compute the same available balance, both pass the check, and both create a payout. The `atomic()` block prevents partial writes but does not serialize concurrent reads.

**Bug 2: Python arithmetic on fetched rows.** The AI fetched all ledger entries into Python and summed them in a list comprehension. This is wrong for two reasons: (a) it can miss rows committed by concurrent transactions between the SELECT and the sum (though this matters less with the lock fixed), and (b) it fetches N rows to do something PostgreSQL can do in one aggregation with `SUM()`. At scale this becomes a memory and performance issue.

**What I replaced it with:**

```python
# ✅ CORRECTED VERSION
def create_payout(merchant, amount_paise, bank_account_id, idempotency_key):
    with transaction.atomic():
        # Step 1: Row-level lock — serialises all concurrent payout creation
        # for this merchant. Other transactions block here.
        merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

        # Step 2: DB-level aggregation — single query, always reads committed data,
        # no Python loop over fetched rows.
        agg = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
            credits=Sum("amount_paise", filter=Q(entry_type="CREDIT"), default=0),
            debits=Sum("amount_paise", filter=Q(entry_type="DEBIT"), default=0),
        )
        held_agg = Payout.objects.filter(
            merchant=merchant_locked,
            status__in=["PENDING", "PROCESSING"],
        ).aggregate(held=Sum("amount_paise", default=0))

        available = (agg["credits"] - agg["debits"]) - held_agg["held"]

        if available < amount_paise:
            raise InsufficientBalanceError(...)

        payout = Payout.objects.create(merchant=merchant_locked, ...)
    return payout
```

The fix is two changes: add `select_for_update()` so PostgreSQL serialises the check-then-act, and replace Python arithmetic on fetched objects with a `SUM()` aggregation. These two changes are the difference between a correct payout engine and one that silently overdraws accounts under production load.

---

## Design Decisions I'd Highlight

**No stored balance column.** The ledger is the single source of truth. We never risk the balance column and the ledger diverging.

**Held funds via Payout model, not ledger.** Rather than writing DEBIT-on-create + CREDIT-on-failure (noise), we track held funds by summing in-flight payout amounts separately. The ledger only records settled economics.

**Idempotency key locked during processing.** The `is_locked` flag gives concurrent duplicate requests a clear signal: "first request is in flight, retry shortly." This avoids both duplicate creation and silent drops.

**TransactionTestCase for concurrency tests.** Django's `TestCase` wraps every test in a transaction that's never committed, making thread-based concurrency tests impossible — threads can't see each other's writes. `TransactionTestCase` uses real commits, enabling true parallel execution in tests.

**`select_for_update(skip_locked=True)` in the sweeper.** Multiple beat workers or overlapping sweeper runs should not pile up on the same stale payout. `skip_locked=True` means "if this row is locked by another transaction, skip it" — exactly the right behavior for a background sweeper.

# Problems Faced During Development
________________________________________
1. PostgreSQL Password Authentication Failed

Problem:
When running python manage.py migrate, the following error occurred:

psycopg2.OperationalError: connection to server at "localhost" (::1), 
port 5432 failed: FATAL: password authentication failed for user "postgres"

Root Cause:
The .env file had DB_PASSWORD=postgres, but the actual PostgreSQL installation was configured with a different password. As a result, Django was sending incorrect credentials to the database.

How We Fixed It:

Located the .env file in the backend folder
Reset the PostgreSQL password using PowerShell (run as Administrator):
cd "C:\Program Files\PostgreSQL\16\bin"
.\psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'Pass@123';"
Updated the .env file:
DB_PASSWORD=Pass@123
Re-ran migrations successfully

What I Learned:
Always verify database credentials independently before running Django migrations. The .env file must exactly match the credentials configured in PostgreSQL.
________________________________________
2. Django Admin Login Failed Despite Creating Superuser
Problem: After running python manage.py createsuperuser and setting credentials, logging into http://127.0.0.1:8000/admin/ showed:
Please enter the correct username and password for a staff account. 
Note that both fields may be case-sensitive.
Root Cause: The superuser was either created before migrations fully completed, or there was a typo during the interactive createsuperuser prompt. The user existed in the database but authentication kept failing.
How We Fixed It: Bypassed the interactive prompt entirely and used Django shell to force-create a clean superuser:
python
python manage.py shell -c "
from django.contrib.auth.models import User
User.objects.filter(username='admin').delete()
User.objects.create_superuser('admin', 'admin@playto.com', 'admin123')
"
What I Learned: create_superuser() programmatically is more reliable than the interactive prompt because it eliminates typing errors and ensures the user is created cleanly.
________________________________________
3. Payouts App Models Not Visible in Django Admin
Problem: After logging into Django admin, only these sections were visible:
•	Authentication and Authorization
•	Celery Results
•	Periodic Tasks
The custom models — Merchants, Bank Accounts, Ledger Entries, Payouts — were completely missing.
Root Cause: The payouts/admin.py file was never created. Django admin only shows models that are explicitly registered using @admin.register() decorator. Without registration, models are invisible in the admin panel even though they exist in the database.
How We Fixed It: Created payouts/admin.py and registered all models:
python
@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "is_active", "created_at"]

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["merchant", "bank_name", "account_number", "ifsc_code"]

# ... and so on for all models
What I Learned: In Django, models must be explicitly registered in admin.py to appear in the admin panel. The file must be created manually — Django does not auto-register custom models.
________________________________________
4. Celery Worker Crashing on Windows
Problem: Running the standard Celery worker command crashed immediately on Windows:
bash
celery -A config worker --loglevel=info
Root Cause: Celery's default process pool (prefork) uses Unix fork() system calls which are not supported on Windows. Windows handles multiprocessing differently and cannot fork processes the same way Linux does.
How We Fixed It: Added --pool=solo flag which runs Celery in a single-threaded mode compatible with Windows:
bash
celery -A config worker --loglevel=info --pool=solo
What I Learned: Celery is primarily designed for Linux. On Windows, --pool=solo is mandatory for development. In production, this service should always be deployed on Linux (Docker, Railway, Render) where the default prefork pool works correctly and gives true parallel task execution.
________________________________________
5. Root URL Showing 404
Problem: Opening http://127.0.0.1:8000/ in the browser showed:
Page not found (404)
Django tried these URL patterns:
1. admin/
2. health/
3. api/v1/
The empty path didn't match any of these.
Root Cause: This was not actually a bug. The Django backend is a pure API server — it serves JSON responses only. No URL was configured for the root path / because there is no HTML page to serve there. The React frontend is a completely separate service running on port 3000.
How We Fixed It: Nothing needed fixing. The correct URLs are:
•	http://localhost:3000 — React dashboard (the actual UI)
•	http://127.0.0.1:8000/api/v1/ — Django REST API
•	http://127.0.0.1:8000/admin/ — Django admin panel
What I Learned: In a decoupled architecture (Django backend + React frontend), Django does not serve the frontend. The two services run on different ports. The 404 on / is expected and correct behavior.
________________________________________
6. Concurrency Race Condition (Design Challenge)
Problem: During development, the initial balance check logic was:
python
# WRONG — Race condition possible
merchant = Merchant.objects.get(pk=id)
available = calculate_balance(merchant)  # Python arithmetic
if available >= amount:
    Payout.objects.create(...)  # Another request can slip in here
If two payout requests of ₹60 came in simultaneously for a merchant with ₹100 balance, both could pass the check before either committed — causing an overdraft.
Root Cause: Reading balance and creating the payout were two separate database operations. Between the read and the write, another concurrent request could read the same stale balance and also pass the check.
How We Fixed It: Used PostgreSQL's SELECT FOR UPDATE row-level lock:
python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(pk=id)
    # Now this merchant row is LOCKED
    # Any concurrent request blocks here until we commit
    available = LedgerEntry.objects.filter(...).aggregate(...)
    if available >= amount:
        Payout.objects.create(...)
    # Lock released on commit
What I Learned: Python-level locks (threading.Lock) don't work across multiple Django worker processes. Only database-level locks work reliably in a multi-process production environment. select_for_update() is the correct tool for check-then-act operations on financial data.
________________________________________
7. Idempotency Race Condition (Design Challenge)
Problem: Two identical requests with the same Idempotency-Key arriving at exactly the same millisecond could both pass the "have I seen this key?" check and both create payouts — duplicating the transaction.
Root Cause: Django's get_or_create() is not atomic under high concurrency. It does a SELECT then INSERT internally, and two concurrent requests can both SELECT (finding nothing) and both attempt INSERT.
How We Fixed It: Used the database UNIQUE(merchant, key) constraint as the true guard. When two requests race, the database allows exactly one INSERT. The second gets an IntegrityError which we catch and handle gracefully:
python
try:
    idem_key, created = IdempotencyKey.objects.get_or_create(...)
except IntegrityError:
    # Lost the race — fetch what the winner created
    idem_key = IdempotencyKey.objects.get(merchant=merchant, key=raw_key)
    created = False
What I Learned: Database unique constraints are the only reliable idempotency guard under concurrency. Application-level checks always have a race window. Let the database enforce uniqueness and handle the exception at the application layer.
________________________________________
Summary Table
#	Problem	Type	Fixed By
1	PostgreSQL password mismatch	Configuration	Corrected .env file
2	Admin login failing	Authentication	Force-created user via Django shell
3	Models missing from admin	Missing file	Created payouts/admin.py
4	Celery crashing on Windows	OS compatibility	Added --pool=solo flag
5	Root URL showing 404	Misunderstanding	Not a bug — expected behavior
6	Concurrent payout overdraft	Concurrency	select_for_update() DB lock
7	Duplicate idempotency keys	Race condition	DB unique constraint + IntegrityError catch
