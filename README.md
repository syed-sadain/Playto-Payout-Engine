# Playto Payout Engine

> Cross-border payment payout infrastructure for Indian merchants — built for the Playto Founding Engineer challenge.

**Stack:** Django 4.2 · DRF · PostgreSQL · Celery + Redis · React 18 · Tailwind CSS · Docker

---

## Architecture Overview

```
┌─────────────┐     POST /api/v1/payouts      ┌─────────────────────┐
│  React SPA  │ ──────────────────────────────► │   Django DRF API    │
│  (Port 3000)│ ◄────────────────────────────── │   (Port 8000)       │
└─────────────┘     JSON response              └──────────┬──────────┘
                                                          │ enqueue task
                    ┌─────────────────────────────────────▼──────────┐
                    │              Redis (Broker)                     │
                    └─────────────────────────────────────┬──────────┘
                                                          │
                    ┌─────────────────────────────────────▼──────────┐
                    │           Celery Worker                         │
                    │  • process_payout_task  (70% success)           │
                    │  • retry_stale_payouts  (every 30s via Beat)    │
                    └─────────────────────────────────────┬──────────┘
                                                          │
                    ┌─────────────────────────────────────▼──────────┐
                    │              PostgreSQL                          │
                    │  merchants · bank_accounts · ledger_entries     │
                    │  payouts · idempotency_keys                     │
                    └─────────────────────────────────────────────────┘
```

---

## Quick Start (Docker — Recommended)

```bash
git clone https://github.com/yourhandle/playto-payout-engine
cd playto-payout-engine

# Start all services: DB, Redis, API, Celery Worker, Beat, Frontend
docker-compose up --build

# API: http://localhost:8000
# Dashboard: http://localhost:3000
# Admin: http://localhost:8000/admin/      
------------------------------------Admin-login-password-----------------------------------------------------
Now Login
Go to http://127.0.0.1:8000/admin/
Username: admin
Password: admin123
Make sure there are no spaces before or after when typing.      
                                                   
```

The API container runs `migrate` + `seed_data` on startup automatically.

---

## Manual Setup (Local Dev)

### Prerequisites
- Python 3.12+
- Node 20+
- PostgreSQL 16+
- Redis 7+

### Backend

```bash
cd backend

# Create and activate virtualenv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your DB credentials

# Create database
createdb playto_payout

# Run migrations
python manage.py migrate

# Seed merchants and credit history
python manage.py seed_data

# Start Django dev server
python manage.py runserver

# In a separate terminal — start Celery worker
celery -A config worker --loglevel=info

# In a third terminal — start Celery Beat (scheduler)
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm start
# Opens http://localhost:3000
```

---

## API Reference

All endpoints return JSON. Amounts are always in **paise** (integer).

### Merchants

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/v1/merchants/` | List all active merchants |
| `GET` | `/api/v1/merchants/{id}/` | Merchant detail + balance breakdown |
| `GET` | `/api/v1/merchants/{id}/ledger/` | Ledger entries (last 100) |

#### Balance Response
```json
{
  "id": "uuid",
  "name": "Arjun Sharma Designs",
  "balance": {
    "available_paise": 285000,
    "held_paise": 45000,
    "ledger_balance_paise": 330000,
    "total_credits_paise": 330000,
    "total_debits_paise": 0,
    "available_inr": "₹2850.00",
    "held_inr": "₹450.00",
    "ledger_balance_inr": "₹3300.00"
  },
  "bank_accounts": [...]
}
```

### Payouts

| Method | URL | Headers | Description |
|--------|-----|---------|-------------|
| `GET` | `/api/v1/merchants/{id}/payouts/` | — | List payouts |
| `POST` | `/api/v1/merchants/{id}/payouts/` | `Idempotency-Key: <uuid>` | Create payout |
| `GET` | `/api/v1/merchants/{id}/payouts/{pid}/` | — | Payout detail |
| `POST` | `/api/v1/payouts/` | `Idempotency-Key: <uuid>`, `X-Merchant-Id: <uuid>` | Flat create |

#### Create Payout Request
```bash
curl -X POST http://localhost:8000/api/v1/merchants/{merchant_id}/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "amount_paise": 50000,
    "bank_account_id": "bank-account-uuid"
  }'
```

#### Create Payout Response (201)
```json
{
  "id": "payout-uuid",
  "amount_paise": 50000,
  "amount_inr": "₹500.00",
  "status": "PENDING",
  "bank_account": {
    "bank_name": "HDFC Bank",
    "masked_account": "****0001"
  },
  "attempt_count": 0,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### Error Responses

| Status | Scenario |
|--------|----------|
| `400` | Missing/invalid Idempotency-Key or body |
| `404` | Merchant or bank account not found |
| `409` | First request still in flight (retry) |
| `422` | Insufficient balance |

---

## Running Tests

```bash
cd backend

# All tests
python manage.py test payouts --verbosity=2

# Specific test classes
python manage.py test payouts.tests.ConcurrentPayoutTest
python manage.py test payouts.tests.IdempotencyTest
python manage.py test payouts.tests.StateMachineTest
python manage.py test payouts.tests.LedgerIntegrityTest
```

**Note:** Concurrency tests use `TransactionTestCase` (not `TestCase`) so real DB transactions are used, enabling true concurrent thread testing.

---

## Seed Data

The seed script creates 3 merchants with credit history:

| Merchant | Credits Seeded | Available Balance |
|---------|---------------|------------------|
| Arjun Sharma Designs | 4 credits | ~₹3,300 |
| PixelForge Studio | 3 credits | ~₹4,300 |
| Meera Krishnan Consulting | 4 credits | ~₹9,500 |

```bash
# Re-seed (clear and reseed)
python manage.py seed_data --clear
```

---

## Deployment (Render / Railway)

### Environment Variables to Set
```
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(50))">
DEBUG=False
DATABASE_URL=<provided by platform>
REDIS_URL=<provided by platform>
ALLOWED_HOSTS=<your-domain.onrender.com>
CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

### Start Commands
- **API (web):** `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4`
- **Worker:** `celery -A config worker --loglevel=info --pool=solo`
- **Beat:** `celery -A config beat --loglevel=info`



#### copy the below commands on terminal and run the  whole project [Easy to run] 

 cd C:\Users\ssada\Downloads\playto-payout-engine\playto-payout-engine
 Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; python manage.py runserver"; `
 Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; celery -A config worker --loglevel=info --pool=solo"; `
 Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; celery -A config beat --loglevel=info"; `
 Start-Process powershell -ArgumentList "cd frontend; npm start"


---

## Project Structure

```
playto-payout-engine/
├── backend/
│   ├── config/
│   │   ├── settings.py        # All Django config + Celery
│   │   ├── urls.py            # Root URL routing
│   │   ├── celery.py          # Celery app instance
│   │   └── wsgi.py
│   ├── payouts/
│   │   ├── admin.py           # Django admin registrations
│   │   ├── models.py          # Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
│   │   ├── services.py        # All business logic (locking, balance, state machine)
│   │   ├── views.py           # Thin API views (delegate to services)
│   │   ├── serializers.py     # DRF serializers
│   │   ├── tasks.py           # Celery tasks (processor + sweeper)
│   │   ├── urls.py            # API routes
│   │   ├── tests.py           # Concurrency + idempotency + state machine tests
│   │   └── management/
│   │       └── commands/
│   │           └── seed_data.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── manage.py
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router + QueryClient
│   │   ├── index.js           # React entrypoint
│   │   ├── index.css          # Tailwind + custom fonts
│   │   ├── services/
│   │   │   └── api.js         # Axios API client
│   │   └── components/
│   │       ├── dashboard/
│   │       │   ├── Dashboard.js
│   │       │   ├── BalanceCard.js
│   │       │   ├── LedgerTable.js
│   │       │   └── MerchantSelect.js
│   │       └── payouts/
│   │           ├── PayoutForm.js
│   │           └── PayoutTable.js
│   ├── public/index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── EXPLAINER.md