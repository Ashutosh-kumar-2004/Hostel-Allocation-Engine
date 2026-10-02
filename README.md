# Policy-Driven Hostel Allocation Engine
### P03 Specification v2.0 · University Residential Life SaaS Platform

An enterprise-grade, deterministic hostel allocation and vacancy promotion platform built with **Python 3.12 & Django 5.x**, featuring multi-objective mathematical optimization, single-hostel jurisdictional gates, DPDP Act 2023 lifestyle compatibility scoring, dynamic 48-hour waiting list promotions, cryptographic QR letter publication, and environment-driven dual-database architecture (SQLite & Turso/libSQL).

---

## 🔑 Test Credentials & Demo Accounts

The database comes pre-seeded with demonstrator accounts across all system roles. You can immediately log in to test any role:

| Role | Username / Student ID | Password | Jurisdiction / Scope | Access Level & Key Features |
| :--- | :--- | :--- | :--- | :--- |
| **System Administrator** | `admin` | `admin123` | Campus-Wide (All Hostels) | Full campus governance, cycle creation, hostel/room inventory CRUD, warden appointments, and global solver runs. |
| **Hostel Warden (BH-4)** | `warden` | `warden123` | Hostel H-4 (BH-4 Boys Residence) | Single-hostel jurisdictional locking: review draft allocations, execute 2-way resident swaps, manual bed reassignments, room change approvals, and check-in key issuance. |
| **Hostel Warden (BH-1)** | `rajesh.warden` | `warden123` | Hostel H-1 (BH-1 Boys Residence) | Secondary warden account to test multi-hostel scope isolation. |
| **Student (Mutual Roommate #1)** | `12300001` | `student123` | Student Portal (Self-Service) | Formed verified mutual pair with `12300002`; view confirmed co-allocation, lifestyle profile, and digital letter. |
| **Student (Room Change Applicant)** | `12300002` | `student123` | Student Portal (Self-Service) | Submitted active Room Change Request to AC room due to dust allergies; mutual pair with `12300001`. |
| **Student (Waitlisted Candidate)** | `12300030` | `student123` | Student Portal (Self-Service) | Candidate in Waiting List Queue #1; requires ground-floor wheelchair accessible room; tests 48h vacancy promotion timer. |
| **Student (Allocated Resident)** | `12300901` | `student123` | Student Portal (Self-Service) | Verified applicant with active allocation and published allotment letter. |
| **Student (Female Candidate)** | `12300004` | `student123` | Student Portal (Self-Service) | Female applicant allocated to Gargi Hall of Residence (GH-1); tests gender constraint isolation. |

---

## 🏛️ System Architecture & Workflow Guide

A detailed, end-to-end architecture breakdown with Mermaid sequence diagrams, state machines, and complete module specifications is documented in:

👉 **[ARTITECTURE_FLOW.md](ARTITECTURE_FLOW.md)**

### Core Feature Matrix:
* **M1 — Campus Inventory Engine**: Real-time interactive bed occupancy matrix across multi-capacity rooms (Single, Double, Triple, Dorm 4+), cooling tiers (AC, Cooler, Natural), and ground-floor accessibility ramps.
* **M2 — Intake Cycles & Applications**: Structured admission cycles enforcing the strict **`123XXXXX`** 8-digit student registration number format.
* **M3 — Policy-Driven Eligibility Ledger**: Modular rule evaluation engine (Distance $\ge 30\text{ km}$, CGPA cutoffs, Fee clearance, Disciplinary checks).
* **M4 — Student Preference & Roommate Matching**: Ranked preferences (Rank #1, #2, #3) with verified bilateral mutual roommate handshake confirmation.
* **M5 — Consented Lifestyle Compatibility Engine**: DPDP Act 2023 compliant vectorized scoring (Sleep 40%, Study Noise 30%, Cleanliness 20%, Guest Tolerance 10%).
* **M6 — Deterministic Allocation Solver**: Constrained multi-objective optimization solver with What-If simulation sandboxing.
* **M7 — Warden Review Gate & Human Override**: Single-hostel jurisdictional locking with atomic two-way resident swaps and mandatory justification audit logging.
* **M8 — Dynamic Waiting List & Promotion Engine**: Gapless queue indexing ($1, 2, 3\dots$) with automated 48-hour vacancy promotion and gender-constrained manual offer modal.
* **M9 — Cryptographic Publication & Key Gate**: Immutable digital letters with SHA-256 verification QR codes and desk check-in physical brass key issuance.

---

## 🛠️ Technology Stack

* **Backend Framework**: Django 5.1.x (Python 3.12)
* **Databases**:
  * **Development**: Local SQLite (`db.sqlite3`)
  * **Production**: Turso Cloud / libSQL (`django-libsql-backend` over HTTP)
* **Frontend & UX**:
  * TailwindCSS (Utility styling)
  * Alpine.js (Reactive modals, dynamic dropdown filtering, state management)
  * HTMX (Sub-second asynchronous updates)
* **Security & Compliance**: DPDP Act 2023 consented questionnaire storage, SHA-256 digital signature hashes, CSRF protection, and immutable audit logs.
* **Containerization**: Docker multi-stage container with `docker-entrypoint.sh` bootstrap.

---

## 🌐 Environment Configuration & Database Switch

The application automatically selects its database engine based on the `ENVIRONMENT` environment variable:

```
ENVIRONMENT=development  ──▶  Local SQLite (db.sqlite3)
ENVIRONMENT=production   ──▶  Turso / libSQL (using TURSO_DATABASE_URL & TURSO_AUTH_TOKEN)
```

### Environment Files:
* **Template File**: [`.env.example`](.env.example)
* **Active Secrets File**: `.env` *(ignored by Git)*

### `.env` File Example:
```ini
# Environment Mode
ENVIRONMENT=development
DJANGO_SETTINGS_MODULE=config.settings
SECRET_KEY=your-secure-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,.onrender.com
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://*.onrender.com

# Turso / libSQL (Required when ENVIRONMENT=production)
TURSO_DATABASE_URL=libsql://your-db-org.turso.io
TURSO_AUTH_TOKEN=your-turso-jwt-auth-token

# Institution Context
DEFAULT_INSTITUTION_ID=inst_demo_university_001

# Cache (Optional in development)
REDIS_URL=redis://localhost:6379/0
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone & Set Up Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/rpl.git
cd rpl

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # On Windows
# source .venv/bin/activate  # On Linux/macOS
```

### 2. Install Dependencies
```bash
pip install -r requirements/dev.txt
```

### 3. Initialize Environment & Run Migrations
```bash
# Copy example environment file
copy .env.example .env

# Run database migrations (automatically seeds demonstrator data if empty!)
python manage.py migrate
```

### 4. Start Development Server
```bash
python manage.py runserver
```
Visit **http://localhost:8000** in your browser.

---

## ☁️ Production Deployment Guide (Render / Turso / Docker)

### Deploying on Render:
1. Create a new **Web Service** on Render and connect your Git repository.
2. Select runtime: **Python 3**.
3. Set **Build Command**:
   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --noinput
   ```
4. Set **Start Command**:
   ```bash
   gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
   ```
5. Add the following **Environment Variables** in Render Dashboard:
   * `ENVIRONMENT` = `production`
   * `TURSO_DATABASE_URL` = `libsql://your-db-org.turso.io`
   * `TURSO_AUTH_TOKEN` = `your-turso-auth-token`
   * `SECRET_KEY` = *(generate secure key)*
   * `ALLOWED_HOSTS` = `*.onrender.com`
   * `CSRF_TRUSTED_ORIGINS` = `https://*.onrender.com`
   * `SECURE_SSL_REDIRECT` = `False`

### Automated Database Seeding:
When the production database on Turso is freshly created and contains no tables or records:
1. `python manage.py migrate` applies all schema tables.
2. The `post_migrate` signal automatically triggers `seed_sample_data`, populating all hostels, blocks, rooms, eligibility rules, and `123XXXXX` student applications.
3. The built-in `AutoSeedMiddleware` provides a second safety net, ensuring the database is instantly ready on the very first HTTP request.

---

## 🧪 Testing & Verification

Run the automated test suites to verify database selection, gender constraints, and seed formatting:

```bash
# Run environment-driven database selection tests
python scratch/test_environment_database_switch.py

# Run gender isolation & dropdown constraints tests
python scratch/test_dropdown_gender_constraints.py

# Run system checks
python manage.py check
```

---

## 📄 License
Academic and institutional distribution under the University Campus Housing Software License.
