# Policy-Driven Hostel Allocation Engine (P03 Specification v2.0)
## System Architecture & Complete Workflow Guide

---

## 1. Executive Summary & Core Mission

The **Policy-Driven Hostel Allocation Engine** is an enterprise-grade academic residential management platform designed to solve the complex logistical, ethical, and regulatory challenges of higher-education campus housing.

Traditional hostel allotment suffers from manual spreadsheets, non-transparent waiting lists, lack of auditability, roommate lifestyle mismatches, and gender policy violations. This engine replaces ad-hoc assignments with a **deterministic, policy-governed mathematical allocation engine** backed by human-in-the-loop governance gates, cryptographic verification, DPDP Act 2023 privacy safeguards, and a dual-database cloud architecture.

```mermaid
graph TD
    A[Campus Inventory & Hostels] --> D[Allocation Engine Solver M6]
    B[Student Applications 123XXXXX] --> C[Eligibility Engine M3]
    C -->|Eligible Pool| D
    E[Ranked Preferences M4] --> D
    F[Lifestyle Compatibility M5] --> D
    D -->|Draft Generation| G[Warden Review Gate M7]
    G -->|Human Override & Approval| H[Cryptographic Publication M9]
    D -->|Unassigned Pool| I[Dynamic Waiting List M8]
    I -->|Automatic Promotion on Vacancy| G
    H -->|Digital Letter & QR Verification| J[Physical Key Check-In]
```

---

## 2. High-Level System Architecture

The application is structured into decoupled, domain-driven Django apps running on top of an environment-driven persistence layer:

```mermaid
graph TB
    subgraph ClientLayer ["Client Layer (SaaS Interface)"]
        UI_Admin["Admin Console (Full Campus View)"]
        UI_Warden["Warden Portal (Scoped Single Hostel)"]
        UI_Student["Student Portal (Self-Service & Verification)"]
    end

    subgraph AppLayer ["Django Core & Application Services"]
        AUTH["Role-Based Authentication & Context Processors"]
        M1["apps.inventory (Hostels, Blocks, Floors, Rooms, Beds)"]
        M2["apps.applications (Cycles, Applicants, Demographics)"]
        M3["apps.eligibility (Policy Rules Ledger)"]
        M4["apps.preferences (Ranked Choices & Mutual Roommates)"]
        M5["apps.compatibility (Consented Vector Synergy)"]
        M6["apps.allocation (Deterministic Multi-Objective Solver)"]
        M7["apps.review (Human Review Gate & Reassignments)"]
        M8["apps.waitlist (Dynamic 48h Vacancy Promotions)"]
        M9["apps.publication (Digital Letters & QR Keys)"]
        AUDIT["apps.audit (Immutable Ledger)"]
        NOTIF["apps.notifications (Real-time In-App Alerts)"]
    end

    subgraph DataLayer ["Persistence Layer (Dual Architecture)"]
        DEV_DB[("Local SQLite (db.sqlite3) - Development")]
        PROD_DB[("Turso / libSQL (HTTP Distributed) - Production")]
    end

    UI_Admin --> AUTH
    UI_Warden --> AUTH
    UI_Student --> AUTH

    AUTH --> M1
    AUTH --> M2
    AUTH --> M3
    AUTH --> M4
    AUTH --> M5
    AUTH --> M6
    AUTH --> M7
    AUTH --> M8
    AUTH --> M9

    M6 --> AUDIT
    M7 --> AUDIT
    M8 --> AUDIT
    M9 --> AUDIT

    M7 --> NOTIF
    M8 --> NOTIF
    M9 --> NOTIF

    AppLayer -->|ENVIRONMENT=development| DEV_DB
    AppLayer -->|ENVIRONMENT=production| PROD_DB
```

---

## 3. End-to-End Operational Lifecycle Workflow

The lifecycle flows through 9 distinct operational phases from initial campus setup to student physical check-in:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as System Administrator
    actor Student as Student Candidate
    actor Warden as Hostel Warden
    participant Engine as Allocation Engine (M6)
    participant Waitlist as Waiting List (M8)
    participant Pub as Publication & Gate (M9)

    Admin->>Admin: 1. Setup Inventory (Hostels, Rooms, Beds, Cooling, Accessibility)
    Admin->>Admin: 2. Open Allocation Cycle & Define Eligibility Rules
    Student->>Student: 3. Register with 123XXXXX ID & Complete Demographics
    Student->>Student: 4. Submit Ranked Preferences (1-3) & Roommate Requests
    Student->>Student: 5. Complete Lifestyle Questionnaire (DPDP Consent)
    Admin->>Engine: 6. Execute Allocation Solver Run
    Engine-->>Admin: Draft Generated (Assigned + Unassigned Waiting List)
    Admin->>Warden: 7. Handover Draft to Hostel Wardens for Scoped Review
    Warden->>Warden: 8. Verify Allocations, Apply 2-Way Swaps or Reassignments
    Warden->>Admin: 9. Record Formal Warden Approval & Sign-Off
    Admin->>Pub: 10. Officially Publish Draft & Generate Cryptographic Letters
    Pub-->>Student: 11. Dispatch Digital Allocation Letter with SHA-256 QR Code
    Student->>Pub: 12. Present Letter at Warden Desk, Inspect QR, Issue Physical Keys
    Note over Waitlist,Engine: When Cancellations Occur:
    Waitlist->>Waitlist: Vacancy Freed -> Trigger Auto-Promotion -> 48h Window
```

---

## 4. Detailed Module Architecture & Mechanics

### Module 1: Campus Inventory Engine (`apps.inventory`)
* **Hierarchical Structure**: `Hostel` $\rightarrow$ `Block` $\rightarrow$ `Floor` $\rightarrow$ `Room` $\rightarrow$ `Bed`.
* **Multi-Capacity Rooms**:
  * Single Occupancy (`SINGLE`)
  * Double Sharing (`DOUBLE`)
  * Triple Sharing (`TRIPLE`)
  * Dormitory 4+ (`DORM`)
* **Cooling Infrastructure**:
  * Central / Split Air Conditioning (`AC`)
  * Desert / Evaporative Cooler (`COOLER`)
  * Natural Ventilation / Ceiling Fan (`NONE`)
* **Ground-Floor Accessibility**: Rooms and beds marked `is_accessible=True` are physically equipped with wheelchair ramps, roll-in bathrooms, and wide doorways, strictly reserved for candidates with documented accessibility requirements.
* **Interactive Bed Map**: Visual color-coded matrix displaying real-time bed states (`AVAILABLE`, `OCCUPIED`, `MAINTENANCE`, `RESERVED`).

---

### Module 2: Intake Cycles & Candidate Applications (`apps.applications`)
* **Academic Cycles**: Time-boxed intake periods (e.g. `AY2026-AUTUMN`) with strict open and close dates.
* **Student Identifier Validation**: Strict format enforcement requiring 8 digits starting with `123` (`123XXXXX`, e.g., `12300001`, `12300030`).
* **Demographic & Merit Data**: Tracks verified distance from home campus (km), academic CGPA (0.00 to 10.00), disciplinary history, and fee clearance status.

---

### Module 3: Policy-Driven Eligibility Ledger (`apps.eligibility`)
* **Configurable Rule Types**:
  * `DISTANCE`: Minimum travel distance threshold (e.g., $\ge 30\text{ km}$).
  * `ACADEMIC`: Minimum CGPA merit cutoff (e.g., $\ge 6.0$).
  * `DISCIPLINARY`: Maximum disciplinary demerit points allowed ($= 0$).
  * `FEE_CLEARED`: Verified tuition and residential dues clearance.
* **Hard vs. Soft Constraints**: Hard rules strictly disqualify non-compliant applicants; soft rules feed tie-breaking priority scores.
* **Batch Verification Engine**: Evaluates hundreds of candidates in sub-second execution with detailed pass/fail audit logs.

---

### Module 4: Student Preferences & Roommate Pairing (`apps.preferences`)
* **Ranked Choices**: Students submit Rank #1 (Weight: 100%), Rank #2 (Weight: 60%), and Rank #3 (Weight: 30%) selections of preferred hostel, room type, and cooling.
* **Mutual Roommate Verification**:
  * Candidate A requests Candidate B ($A \rightarrow B$).
  * Only when Candidate B reciprocal-requests Candidate A ($B \rightarrow A$) does the pair become **`MUTUAL_CONFIRMED`**.
  * Mutual pairs receive atomic co-allocation into the same room.
* **Gender Policy Isolation**: Preference dropdowns strictly filter and prevent female applicants from selecting male hostels and vice-versa.

---

### Module 5: Consented Lifestyle Compatibility Engine (`apps.compatibility`)
* **DPDP Act 2023 Compliance**: Explicit consent is required before processing personal lifestyle habits. Non-consenting students are assigned without personality evaluation.
* **Vectorized Scoring Dimensions**:
  $$\text{Synergy Score} = 0.40 \cdot S_{\text{sleep}} + 0.30 \cdot S_{\text{study}} + 0.20 \cdot S_{\text{clean}} + 0.10 \cdot S_{\text{guest}}$$
  1. **Sleep Schedule (40%)**: Early Bird ($<11\text{ PM}$), Flexible, Night Owl ($>1\text{ AM}$).
  2. **Study Environment (30%)**: Absolute Silence, Ambient / Music, Collaborative.
  3. **Cleanliness Standard (20%)**: High/Spic-and-Span, Moderate, Relaxed.
  4. **Guest Boundaries (10%)**: Strict privacy ($1$) to social hub ($5$).
* **Pairwise Compatibility Sandbox**: Wardens and admins can simulate any two applicants to preview lifestyle harmony and potential room friction.

---

### Module 6: Deterministic Multi-Objective Allocation Solver (`apps.allocation`)
* **Mathematical Optimization**: Formulated as a constrained multi-criteria matching problem:
  * **Objective**: Maximize preference rank satisfaction $+$ mutual roommate co-locations $+$ lifestyle compatibility synergy.
  * **Hard Constraints**:
    1. Gender isolation (no cross-gender assignments).
    2. Capacity limits (no room over-allocation).
    3. Accessibility priority (wheelchair applicants guaranteed accessible beds).
    4. Room sharing limits.
* **What-If Simulation Sandbox**: Admins can run trial drafts with varying parameters (e.g. changing distance weight from 50% to 70%) to compare satisfaction metrics before committing.

---

### Module 7: Warden Review Gate & Human Override (`apps.review`)
* **Jurisdictional Locking**: Wardens assigned to Hostel A cannot see or modify assignments in Hostel B.
* **Two-Way Resident Swap**:
  * Atomically swaps two students across rooms while enforcing gender and accessibility constraints.
  * Prevents `UniqueConstraint` collisions using two-phase transactional swap logic.
* **Vacant Bed Reassignments**: Reassigns a student from one bed to an unoccupied bed within the warden's hostel.
* **Mandatory Justification**: No override can be committed without a non-empty audit reason.

---

### Module 8: Dynamic Waiting List & Promotion Engine (`apps.waitlist`)
* **Gapless Priority Indexing**: Active candidates maintain sequential queue ranks ($1, 2, 3\dots$) without gaps.
* **Event-Driven Auto-Promotion**:
  * Triggered whenever an allocated student cancels, declines, or their offer expires.
  * Automatically scans for the highest-priority eligible candidate of the matching gender and accessibility tier.
  * Dispatches a time-boxed 48-hour bed offer.
* **Manual Bed Offer Modal**: Scoped dropdowns display only vacant beds compliant with the student's gender policy.

---

### Module 9: Cryptographic Publication & Key Issuance Gate (`apps.publication`)
* **Immutable Digital Letters**: Once a draft is sealed and published, letters are stamped with a unique document reference (e.g. `AL-AY2026-AUTUMN-BH-4-12300001`).
* **Cryptographic QR Code**: Generated via SHA-256 hash of document reference and assignment ID (`hashlib.sha256(ref:id).hexdigest()[:16]`).
* **Desk Check-In & Key Issuance**: Front desk staff scan the student's letter, verify the QR authenticity, enter the physical brass key number, and mark the student officially checked in.

---

## 5. Dual Database Architecture (SQLite vs. Turso libSQL)

The engine supports seamless multi-cloud persistence without changing business code:

```mermaid
graph LR
    subgraph EnvSelector ["settings.py Automatic Selector"]
        ENV_VAR["ENVIRONMENT"]
    end

    subgraph DevMode ["ENVIRONMENT=development"]
        SQLITE_BACKEND["django.db.backends.sqlite3"]
        SQLITE_FILE[("db.sqlite3 (Local File)")]
    end

    subgraph ProdMode ["ENVIRONMENT=production"]
        LIBSQL_BACKEND["django_libsql"]
        TURSO_CLOUD[("Turso Cloud (libSQL over HTTP)")]
    end

    ENV_VAR -->|'development'| SQLITE_BACKEND --> SQLITE_FILE
    ENV_VAR -->|'production'| LIBSQL_BACKEND --> TURSO_CLOUD
```

* **Local Development**: Uses standard `db.sqlite3` with zero network latency and no cloud dependencies.
* **Production Deployment**: Uses `django-libsql-backend` connected to Turso via `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`.
* **Zero-Leakage**: Secrets remain strictly within environment variables and `.env` (ignored by Git).
* **Auto-Seed on Fresh DB**: If the connected database (SQLite or Turso) is empty, `post_migrate` signals and `AutoSeedMiddleware` automatically seed full P03 demonstrator data.

---

## 6. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    Hostel ||--o{ Block : contains
    Block ||--o{ Floor : contains
    Floor ||--o{ Room : contains
    Room ||--o{ Bed : contains
    Hostel ||--o{ WardenHostelAssignment : assigned_to

    AllocationCycle ||--o{ Application : receives
    AllocationCycle ||--o{ EligibilityRule : governs
    AllocationCycle ||--o{ AllocationDraft : runs
    AllocationCycle ||--o{ WaitlistEntry : tracks

    Application ||--o{ Preference : ranks
    Application ||--o| CompatibilityResponse : consents
    Application ||--o| AllocationAssignment : allocated_to
    Application ||--o| RoommateRequest : initiates

    AllocationDraft ||--o{ AllocationAssignment : contains
    AllocationDraft ||--o| PublicationRecord : seals
    AllocationDraft ||--o{ WardenApproval : approved_by

    AllocationAssignment ||--|| Bed : occupies
    AllocationAssignment ||--o| AllocationLetter : generates
    AllocationAssignment ||--o{ Override : modified_by
```

---

## 7. State Machine Transitions

### Candidate Application State Machine
```mermaid
stateDiagram-v2
    [*] --> SUBMITTED : Student Registers (123XXXXX)
    SUBMITTED --> ELIGIBLE : M3 Rules Evaluate Pass
    SUBMITTED --> INELIGIBLE : M3 Hard Rule Violations
    ELIGIBLE --> ALLOCATED : M6 Solver Draft Assignment
    ELIGIBLE --> WAITLISTED : Beds Full (M8 Queue)
    ALLOCATED --> PUBLISHED : Human Review Sign-Off (M9)
    ALLOCATED --> CANCELLED : Student Withdrawal
    WAITLISTED --> ALLOCATED : Vacancy Auto-Promotion
    PUBLISHED --> CHECKED_IN : Physical Key Issued
```

### Waiting List Entry State Machine
```mermaid
stateDiagram-v2
    [*] --> ACTIVE : Placed in Queue (Priority 1..N)
    ACTIVE --> OFFERED : Bed Vacancy Identified (48h Timer)
    OFFERED --> ACCEPTED : Student Confirms Bed Allotment
    OFFERED --> DECLINED : Student Declines Offer
    OFFERED --> EXPIRED : 48h Acceptance Window Closes
    DECLINED --> [*] : Promoted to Next in Line
    EXPIRED --> [*] : Promoted to Next in Line
    ACCEPTED --> [*] : Converted to Confirmed Allocation
```

---

## 8. Directory & Service Layout

```
rpl/
├── apps/
│   ├── allocation/        # M6 Multi-Objective Solver & What-If Simulations
│   ├── applications/      # M2 Intake Cycles & Candidate Profile Management
│   ├── audit/             # Cross-cutting Immutable Action Audit Ledger
│   ├── compatibility/     # M5 Consented DPDP Act Lifestyle Compatibility Engine
│   ├── core/              # SaaS Authentication, Dashboard, Middleware, Auto-Seed
│   ├── eligibility/       # M3 Configurable Policy Rules & Clearance Engine
│   ├── inventory/         # M1 Campus Hostels, Blocks, Rooms, Beds & Bed Map
│   ├── notifications/     # Real-time In-App Notification Center
│   ├── preferences/       # M4 Ranked Preferences & Mutual Roommate Requests
│   ├── publication/       # M9 Sealed Digital Letters, QR Keys & Check-In
│   ├── review/            # M7 Warden Scoped Review Gate & Reassignment Overrides
│   └── waitlist/          # M8 Gapless Waiting List & 48h Vacancy Auto-Promotions
├── config/
│   ├── settings/
│   │   ├── __init__.py    # Dynamic environment-driven settings dispatcher
│   │   ├── base.py        # Core apps, middleware, DB switch, and tokens
│   │   ├── dev.py         # Local development overrides
│   │   └── prod.py        # Production security, SSL headers, and cache fallback
│   ├── urls.py            # Global URL routing
│   └── wsgi.py            # Production WSGI application
├── static/                # Vanilla CSS, SVG icons, and frontend assets
├── templates/             # Semantic HTML5 + TailwindCSS + Alpine.js templates
├── docker-entrypoint.sh   # Container bootstrap: migrations, static, auto-seed
├── Dockerfile             # Multi-stage production container definition
├── docker-compose.yml     # Container orchestration with Redis and Web services
├── requirements.txt       # Production dependencies entrypoint
└── requirements/          # Modular requirements (base, dev, prod)
```
