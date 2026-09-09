# 💰 Playto Payout Engine

> **Cross-border payout infrastructure for Indian merchants, built for the Playto Founding Engineer Challenge.**

A production-oriented payout processing system designed to handle merchant balances, payout creation, asynchronous processing, retries, idempotency, ledger integrity, and concurrent payout requests.

### 🛠️ Tech Stack

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python\&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django\&logoColor=white)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/Django%20REST%20Framework-API-A30000?logo=django\&logoColor=white)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-4169E1?logo=postgresql\&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?logo=redis\&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-Task%20Queue-37814A?logo=celery\&logoColor=white)](https://docs.celeryq.dev/)
[![React](https://img.shields.io/badge/React.js-18+-61DAFB?logo=react\&logoColor=black)](https://react.dev/)
[![Next.js](https://img.shields.io/badge/Next.js-Framework-000000?logo=next.js\&logoColor=white)](https://nextjs.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-UI-06B6D4?logo=tailwindcss\&logoColor=white)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker\&logoColor=white)](https://www.docker.com/)
[![REST API](https://img.shields.io/badge/API-REST-02569B)]()
[![Tests](https://img.shields.io/badge/Tests-Automated-success)]()

---

## 📌 Overview

**Playto Payout Engine** is a full-stack payout infrastructure application for Indian merchants.

The system provides APIs and a merchant dashboard for:

* Merchant account management
* Balance tracking
* Bank account management
* Payout creation
* Idempotent requests
* Concurrent payout protection
* Asynchronous payout processing
* Automatic retries
* Ledger management
* Transaction integrity
* Background scheduling

The backend follows a **service-oriented architecture**, keeping business logic separate from API views and using PostgreSQL transactions and row-level locking where required.

---

# 🏗️ Architecture

```text
                         ┌──────────────────────┐
                         │      React SPA       │
                         │      Port 3000       │
                         └──────────┬───────────┘
                                    │
                              REST / JSON
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Django DRF       │
                         │      Port 8000       │
                         └──────────┬───────────┘
                                    │
                              Enqueue Task
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │        Redis         │
                         │     Message Broker   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                  ┌─────────────────────────────────┐
                  │          Celery Worker          │
                  │                                 │
                  │ • process_payout_task           │
                  │ • retry_stale_payouts           │
                  └────────────────┬────────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │     PostgreSQL       │
                         │                      │
                         │ • merchants         │
                         │ • bank_accounts      │
                         │ • ledger_entries     │
                         │ • payouts            │
                         │ • idempotency_keys   │
                         └──────────────────────┘
```

---

# 🔄 Payout Processing Flow

```text
Merchant
   │
   ▼
Create Payout
   │
   ▼
Validate Request
   │
   ├── Invalid ──────────────► 400 / 404 / 422
   │
   ▼
Check Idempotency Key
   │
   ├── Existing Request ─────► Return Existing Payout
   │
   ▼
Lock Merchant Balance
   │
   ▼
Validate Available Balance
   │
   ├── Insufficient ─────────► 422
   │
   ▼
Create PENDING Payout
   │
   ▼
Enqueue Celery Task
   │
   ▼
Redis Broker
   │
   ▼
Celery Worker
   │
   ├── SUCCESS ──────────────► COMPLETED
   │
   └── FAILURE ──────────────► Retry / FAILED
```

---

# 🔐 Core Engineering Features

## Idempotency

Every payout request supports an `Idempotency-Key`.

This prevents duplicate payouts when the same request is accidentally submitted multiple times due to:

* Network retries
* Client retries
* Browser refreshes
* Duplicate API requests
* Temporary service failures

Example:

```http
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

The same idempotency key will not create multiple payouts.

---

## 🔒 Concurrent Payout Protection

The system protects merchant balances from race conditions during simultaneous payout requests.

Database transactions and row-level locking are used to ensure that two concurrent requests cannot incorrectly spend the same available balance.

Concurrency tests use Django's:

```python
TransactionTestCase
```

instead of the standard `TestCase` to allow real database transactions during concurrent testing.

---

## 💳 Ledger-Based Balance Management

Merchant balances are represented through ledger entries rather than relying only on a mutable balance field.

The system tracks:

```text
Credits
   +
Debits
   =
Ledger Balance
```

And separates:

```text
Available Balance
Held Balance
Ledger Balance
```

Example:

```json
{
  "available_paise": 285000,
  "held_paise": 45000,
  "ledger_balance_paise": 330000
}
```

All monetary values are stored as **integer paise** to avoid floating-point precision issues.

---

## 🔁 Automatic Retry System

Celery handles asynchronous payout processing.

The system includes:

```text
process_payout_task
```

for payout processing and:

```text
retry_stale_payouts
```

for recovering stale payouts.

Celery Beat periodically checks for payouts that require retry processing.

---

# ✨ Features

### 🏦 Merchant Management

* Merchant profiles
* Merchant balances
* Bank account management
* Ledger history

### 💸 Payout Management

* Create payouts
* Payout status tracking
* Payout history
* Bank account validation
* Balance validation

### 🔐 Reliability

* Idempotency
* Database transactions
* Row-level locking
* Concurrent request protection
* Retry handling
* State machine validation

### ⚡ Asynchronous Processing

* Redis message broker
* Celery workers
* Celery Beat scheduler
* Background payout processing

### 🧪 Testing

* Idempotency tests
* Concurrency tests
* State machine tests
* Ledger integrity tests

### 🖥️ Dashboard

* Merchant selection
* Balance overview
* Ledger table
* Payout creation
* Payout history
* Payout status monitoring

---

# 🚀 Quick Start — Docker

Docker is the **recommended way to run the complete application**.

## 1. Clone Repository

```bash
git clone https://github.com/yourhandle/playto-payout-engine.git
cd playto-payout-engine
```

## 2. Start All Services

```bash
docker-compose up --build
```

This starts:

```text
PostgreSQL
Redis
Django API
Celery Worker
Celery Beat
React Frontend
```

### Application URLs

| Service      | URL                          |
| ------------ | ---------------------------- |
| API          | http://localhost:8000        |
| Dashboard    | http://localhost:3000        |
| Django Admin | http://localhost:8000/admin/ |

The API container automatically runs:

```text
migrate
seed_data
```

during startup.

---

# 🔑 Django Admin

Open:

```text
http://127.0.0.1:8000/admin/
```

### Local Development Credentials

```text
Username: admin
Password: admin123
```

> ⚠️ **Security:** These credentials are intended only for local development/demo purposes. Change them before deploying to any public or production environment.

---

# 🛠️ Manual Local Setup

## Prerequisites

Make sure the following are installed:

* Python 3.12+
* Node.js 20+
* PostgreSQL 16+
* Redis 7+

---

# 🐍 Backend Setup

```bash
cd backend
```

### Create Virtual Environment

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
```

For Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your database and Redis configuration.

---

## 🗄️ Create Database

```bash
createdb playto_payout
```

Or create the database manually through PostgreSQL.

---

## 🔄 Run Migrations

```bash
python manage.py migrate
```

---

## 🌱 Seed Demo Data

```bash
python manage.py seed_data
```

To clear and reseed:

```bash
python manage.py seed_data --clear
```

---

# 🚀 Start Backend

```bash
python manage.py runserver
```

API:

```text
http://localhost:8000
```

---

# ⚡ Start Celery Worker

Open another terminal:

```bash
celery -A config worker --loglevel=info
```

Windows users may use:

```bash
celery -A config worker --loglevel=info --pool=solo
```

---

# ⏰ Start Celery Beat

Open another terminal:

```bash
celery -A config beat --loglevel=info
```

For Django database scheduler:

```bash
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

# ⚛️ Frontend Setup

Open another terminal:

```bash
cd frontend
```

Install dependencies:

```bash
npm install --legacy-peer-deps
```

Start frontend:

```bash
npm start
```

Dashboard:

```text
http://localhost:3000
```

---

# 🧑‍💻 One-Command Windows Startup

For Windows PowerShell, from the project root:

```powershell
cd C:\Users\ssada\Downloads\playto-payout-engine\playto-payout-engine

Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; python manage.py runserver"

Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; celery -A config worker --loglevel=info --pool=solo"

Start-Process powershell -ArgumentList "cd backend; venv\Scripts\activate; celery -A config beat --loglevel=info"

Start-Process powershell -ArgumentList "cd frontend; npm start"
```

This launches:

```text
Django API
Celery Worker
Celery Beat
React Frontend
```

in separate PowerShell windows.

---

# 🔌 API Reference

All API endpoints return JSON.

> 💡 **Important:** Monetary amounts are represented as integer **paise** to avoid floating-point rounding problems.

---

## 🏦 Merchant APIs

| Method | Endpoint                         | Description                    |
| ------ | -------------------------------- | ------------------------------ |
| `GET`  | `/api/v1/merchants/`             | List active merchants          |
| `GET`  | `/api/v1/merchants/{id}/`        | Merchant details and balance   |
| `GET`  | `/api/v1/merchants/{id}/ledger/` | Retrieve recent ledger entries |

### Example Balance Response

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
  "bank_accounts": []
}
```

---

# 💸 Payout APIs

| Method | Endpoint                                | Headers                            | Description           |
| ------ | --------------------------------------- | ---------------------------------- | --------------------- |
| `GET`  | `/api/v1/merchants/{id}/payouts/`       | —                                  | List merchant payouts |
| `POST` | `/api/v1/merchants/{id}/payouts/`       | `Idempotency-Key`                  | Create payout         |
| `GET`  | `/api/v1/merchants/{id}/payouts/{pid}/` | —                                  | Payout details        |
| `POST` | `/api/v1/payouts/`                      | `Idempotency-Key`, `X-Merchant-Id` | Flat payout creation  |

---

# 📝 Create Payout

```bash
curl -X POST http://localhost:8000/api/v1/merchants/{merchant_id}/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "amount_paise": 50000,
    "bank_account_id": "bank-account-uuid"
  }'
```

### Response

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

---

# ❌ API Error Handling

| HTTP Status | Scenario                           |
| ----------: | ---------------------------------- |
|       `400` | Invalid request or Idempotency-Key |
|       `404` | Merchant or bank account not found |
|       `409` | Existing request still in progress |
|       `422` | Insufficient available balance     |

---

# 🧪 Testing

Run the complete test suite:

```bash
cd backend
python manage.py test payouts --verbosity=2
```

### Specific Test Suites

```bash
python manage.py test payouts.tests.ConcurrentPayoutTest
```

```bash
python manage.py test payouts.tests.IdempotencyTest
```

```bash
python manage.py test payouts.tests.StateMachineTest
```

```bash
python manage.py test payouts.tests.LedgerIntegrityTest
```

### Test Coverage

The test suite focuses on:

* 🔒 Concurrent payout protection
* 🔁 Idempotent requests
* 🔄 Payout state transitions
* 💰 Ledger integrity
* 🏦 Balance calculations
* ⚡ Transaction safety

---

# 🌱 Seed Data

The seed command creates three demo merchants with transaction history.

| Merchant                  | Credits Seeded | Approx. Available Balance |
| ------------------------- | -------------: | ------------------------: |
| Arjun Sharma Designs      |              4 |                    ₹3,300 |
| PixelForge Studio         |              3 |                    ₹4,300 |
| Meera Krishnan Consulting |              4 |                    ₹9,500 |

Run:

```bash
python manage.py seed_data
```

Reset and reseed:

```bash
python manage.py seed_data --clear
```

---

# ☁️ Deployment

The application can be deployed using platforms such as:

* Render
* Railway
* Docker-based infrastructure

## Environment Variables

```env
SECRET_KEY=<production-secret-key>
DEBUG=False
DATABASE_URL=<postgresql-database-url>
REDIS_URL=<redis-url>
ALLOWED_HOSTS=<your-domain>
CORS_ALLOWED_ORIGINS=<your-frontend-domain>
```

Generate a secure Django secret key:

```bash
python -c "import secrets; print(secrets.token_hex(50))"
```

---

# 🚀 Production Start Commands

### Django API

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4
```

### Celery Worker

```bash
celery -A config worker --loglevel=info --pool=solo
```

### Celery Beat

```bash
celery -A config beat --loglevel=info
```

> ⚠️ Production deployments should use secure secrets, managed PostgreSQL/Redis, restricted CORS/hosts, proper admin credentials, HTTPS, logging, monitoring, and appropriate worker/process configuration.

---

# 📁 Project Structure

```text
playto-payout-engine/
│
├── backend/
│   │
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── wsgi.py
│   │
│   ├── payouts/
│   │   ├── admin.py
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── tasks.py
│   │   ├── urls.py
│   │   ├── tests.py
│   │   │
│   │   └── management/
│   │       └── commands/
│   │           └── seed_data.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── manage.py
│
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── index.js
│   │   ├── index.css
│   │   │
│   │   ├── services/
│   │   │   └── api.js
│   │   │
│   │   └── components/
│   │       ├── dashboard/
│   │       │   ├── Dashboard.js
│   │       │   ├── BalanceCard.js
│   │       │   ├── LedgerTable.js
│   │       │   └── MerchantSelect.js
│   │       │
│   │       └── payouts/
│   │           ├── PayoutForm.js
│   │           └── PayoutTable.js
│   │
│   ├── public/
│   │   └── index.html
│   │
│   ├── package.json
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── nginx.conf
│
├── docker-compose.yml
├── EXPLAINER.md
└── README.md
```

---

# 🧩 Architecture Responsibilities

| Component                 | Responsibility                       |
| ------------------------- | ------------------------------------ |
| **React**                 | Merchant dashboard and payout UI     |
| **Django REST Framework** | API layer                            |
| **Services**              | Core payout business logic           |
| **PostgreSQL**            | Persistent transactional data        |
| **Redis**                 | Celery message broker                |
| **Celery**                | Asynchronous payout processing       |
| **Celery Beat**           | Scheduled retry/sweeper tasks        |
| **Docker**                | Containerized development/deployment |

---

# 💡 Engineering Decisions

### Why PostgreSQL?

PostgreSQL provides strong transactional guarantees and row-level locking required for reliable financial workflows.

### Why Redis + Celery?

Payout processing should not block the API request. Celery moves processing into background workers while Redis acts as the message broker.

### Why Idempotency?

Financial APIs must protect against duplicate operations caused by client retries or network failures.

### Why Integer Paise?

Using integer paise avoids floating-point precision issues when handling monetary values.

### Why Service Layer?

Business-critical payout logic is isolated inside `services.py`, keeping API views thin and easier to test and maintain.

---

# 📸 Screenshots

Add screenshots of the application here:

```text
docs/
├── dashboard.png
├── payout-form.png
├── payout-history.png
└── django-admin.png
```

Example:

```markdown
![Merchant Dashboard](docs/dashboard.png)

![Payout Management](docs/payout-history.png)
```

---

# 🔮 Future Improvements

Potential production enhancements include:

* 🔐 JWT/OAuth authentication
* 🛡️ Role-based access control
* 🔑 Secrets management
* 📊 Prometheus/Grafana monitoring
* 📝 Structured logging
* 🔔 Webhook notifications
* 🏦 Real banking/payment-provider integration
* 🔄 Advanced retry policies
* 🚦 Rate limiting
* 🧾 Audit logs
* 🔍 Distributed tracing
* ☁️ Kubernetes deployment
* 🔐 Encryption of sensitive financial data
* 📈 Real-time payout monitoring

---

# 🎯 Challenge Objectives Demonstrated

This project demonstrates practical experience with:

* Backend architecture
* Django & Django REST Framework
* PostgreSQL transactions
* Database locking
* Idempotency
* Concurrent request handling
* Financial ledger design
* Asynchronous processing
* Celery & Redis
* REST API development
* React frontend development
* Docker
* Automated testing
* Production-oriented system design

---

# 👨‍💻 Author

**Syed Sadain**

**Python Full Stack Developer | Backend Developer | AI/ML Engineer**

🔗 GitHub:
https://github.com/syed-sadain

🔗 LinkedIn:
https://www.linkedin.com/in/syed-sadain-a56ba827/

---

## ⭐ If You Find This Project Useful

Please consider giving the repository a ⭐ on GitHub.

---

**Built with Python, Django, PostgreSQL, Celery, Redis, React.js, Tailwind CSS & Docker.**
