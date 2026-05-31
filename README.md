# Apex

Apex is a workforce-operations suite on Frappe v15, ERPNext, and HRMS. It runs two lifecycles on one platform: the estate-to-resident housing lifecycle and the worker/representative movement lifecycle.

It ships as a single Frappe package (`apex_habitat`) with three modules — **Habitat**, **Salis**, and **Apex Core**. Its defining decision is a **memo-ledger cost model**: every operational cost and stock movement posts to purpose-built, read-only memo ledgers that are isolated from the ERPNext General Ledger. Cost, cross-charge, and on-hand inventory stay fully traceable; financial posting remains a deliberate, human decision.

## Modules

- **Habitat** — accommodation and facilities: spatial inventory (sites, buildings, rooms, beds), resident assignment/transfer/checkout, scheduled safety and cleaning work, maintenance and work orders, custody of issued assets, a decentralized internal store, and lease/utility cost control.
- **Salis** — movement and fleet: a two-division service model on **Transport Request** (`service_line` = Workers vs Representatives), a shared vehicle/driver/fuel/dispatch backbone, vehicle rentals and cost recovery, a native-Frappe **Workflow** approval spine across its submittable documents, and a mobile **driver portal** (`/driver`) with a theme driver, an English/Arabic language toggle, and driver-profile and assigned-vehicle views.
- **Apex Core** — the settings hub: the Single DocTypes **Habitat Settings**, **Salis Settings**, **Apex Integration Settings**, and **Salis Portal Theme** that the functional modules and portal read for thresholds, toggles, default company/cost-center, and portal appearance.

## Architecture

The architecture is documented from a few complementary perspectives; each diagram carries a one-line caption.

### Modules and what each owns

One package hosts three modules. Habitat and Salis own their DocTypes, reports, workspaces, and logic; Apex Core holds the shared settings both read. Every operational write lands in a module-owned memo ledger, never the General Ledger.

```mermaid
flowchart TB
    PKG(["apex_habitat — single package, 3 modules"]):::hub

    subgraph Functional ["Functional modules (own DocTypes, reports, logic)"]
        direction LR
        subgraph HABG ["Habitat — accommodation & facilities"]
            HAB["Housing · safety · maintenance<br/>custody · leasing · internal store"]:::dom
            HLED[("Accommodation + Stock ledgers<br/>memo, no GL")]:::sink
        end
        subgraph SALG ["Salis — movement & fleet"]
            SAL["Transport Request (Workers / Reps)<br/>vehicles · drivers · fuel · dispatch · rentals"]:::dom
            SLED[("Movement cost / recovery<br/>memo, no GL")]:::sink
        end
    end

    CORE["Apex Core — settings hub (Single DocTypes)<br/>Habitat · Salis · Integration · Portal Theme"]:::core

    PKG --> HABG
    PKG --> SALG
    PKG --> CORE
    HAB --> HLED
    SAL --> SLED
    HAB -. reads .-> CORE
    SAL -. reads .-> CORE

    classDef hub fill:#1e3a8a,stroke:#1e3a8a,color:#fff;
    classDef dom fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef core fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;
    classDef sink fill:#f1f5f9,stroke:#475569,color:#334155,stroke-dasharray:4 3;
```

### System context

Black-box view of who and what Apex talks to. Desk users and operations consoles use the standard Frappe session; the `/driver` portal is a themeable, mobile web app — English/Arabic toggle, driver-profile and assigned-vehicle views — that resolves the signed-in user to a driver server-side; two public QR web forms accept rate-limited guest submissions.

```mermaid
flowchart TB
    MGR(["Managers / Supervisors"]):::actor
    FIN(["Finance / Auditor"]):::actor
    DRV(["Drivers"]):::actor
    WRK(["Residents / staff (guest)"]):::actor

    subgraph Clients ["Client surfaces"]
        direction LR
        DESK["Frappe Desk<br/>workspaces · lists · reports"]:::dom
        CONS["Ops consoles<br/>Dispatch · Fuel Approval"]:::dom
        PORTAL["Driver portal /driver"]:::dom
        QR["Public QR web forms"]:::dom
    end

    APEX(["Apex — Habitat · Salis · Apex Core"]):::hub

    subgraph Platform ["Platform apps (required)"]
        direction LR
        FRP["Frappe v15<br/>auth · ORM · Workflow · scheduler"]:::core
        ERP["ERPNext<br/>Company · Project · Cost Center"]:::core
        HRMS["HRMS<br/>Employee · Additional Salary"]:::core
    end

    MGR --> DESK
    MGR --> CONS
    FIN --> DESK
    DRV --> PORTAL
    WRK --> QR

    DESK --> APEX
    CONS -- whitelisted API --> APEX
    PORTAL -- session-scoped API --> APEX
    QR -- guest, rate-limited --> APEX

    APEX --> FRP
    APEX -. Link masters .-> ERP
    APEX -. draft deduction (gated) .-> HRMS

    classDef actor fill:#fff7ed,stroke:#9a3412,color:#7c2d12;
    classDef hub fill:#1e3a8a,stroke:#1e3a8a,color:#fff;
    classDef dom fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef core fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;
```

### Residency data model

Static view of the housing core. A site contains buildings; a building is planned into rooms and beds; an assignment places an employee in a bed and is the unit of occupancy. Every cost it incurs becomes an **Accommodation Ledger** memo row — analytics, never a GL entry.

```mermaid
erDiagram
    ACCOMMODATION_SITE     ||--o{ ACCOMMODATION_BUILDING : contains
    ACCOMMODATION_BUILDING ||--o{ ACCOMMODATION_ROOM : "planned into"
    ACCOMMODATION_ROOM     ||--o{ ACCOMMODATION_BED : holds
    ACCOMMODATION_BED      ||--o{ ACCOMMODATION_ASSIGNMENT : "occupied by"
    EMPLOYEE               ||--o{ ACCOMMODATION_ASSIGNMENT : "housed by"
    ACCOMMODATION_ASSIGNMENT ||--o{ ACCOMMODATION_CHECKOUT : "ends with"
    ACCOMMODATION_ASSIGNMENT ||--o{ ROOM_BED_TRANSFER : "moved by"
    ACCOMMODATION_ASSIGNMENT ||--o{ ACCOMMODATION_LEDGER : "accrues memo cost"

    ACCOMMODATION_ASSIGNMENT {
        Link employee
        Link bed
        Select stay_type "Permanent | Temporary"
        Date expected_checkout_date
    }
    ACCOMMODATION_LEDGER {
        Select ledger_type "Rent | Electricity | Cleaning"
        Select posting_mode "Operational Memo (never GL)"
        Currency employee_daily_share
        Link reversal_of "cancellation mirror"
    }
```

### Approval state machine (Salis)

Dynamic state view. Salis submittable documents move on native Frappe Workflows (in `salis/workflow/`), not custom controllers — **ten documents** in all. Each transition is gated by an allowed role and a Segregation-of-Duties condition (approver ≠ requester); large-scope requests escalate to an Operations tier via the server-derived `needs_operations` flag. **Transport Request** is shown as the representative spine.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> New
    New --> Validated: Validate (Supervisor)
    New --> Rejected: Reject
    Validated --> Approved: Authorize (Regional / Operations)
    Validated --> Rejected: Reject
    Approved --> Scheduled: Schedule (Supervisor)
    Scheduled --> Fulfilled: Confirm
    Approved --> Cancelled: Cancel (Manager)
    Scheduled --> Cancelled: Cancel (Manager)
    Fulfilled --> [*]
    Rejected --> [*]
    Cancelled --> [*]

    note right of Approved
        SoD gate: approver ≠ requester.
        doc_status crosses 0 → 1 here.
    end note
```

The same role + SoD pattern governs the rest of the spine: Fuel Request, Fuel Claim, Fuel Exception Case, Rental Settlement, Salis Payment Request, Dispatch Trip, Driver Clearance, and Support Ticket.

### Request-to-fulfilment sequence

Dynamic view across the wire: a fuel request from the driver portal to a manager approving on the desk console, showing where each guard fires. The portal resolves the driver from the session; the console call runs the per-document project row-scope check; the Workflow applies the role + SoD gate. No GL entry is written.

```mermaid
sequenceDiagram
    autonumber
    actor Driver
    participant Portal as Driver portal (/driver)
    actor Manager
    participant API as Whitelisted API
    participant WF as Workflow engine
    participant Doc as Fuel Request
    participant Ledger as Fuel ledger (memo)

    Driver->>Portal: tap "Request fuel"
    Portal->>API: submit (session cookie)
    API->>API: resolve driver + verify vehicle bound
    API->>Doc: insert (status = Pending)

    Manager->>API: approve (session cookie)
    API->>API: has_permission — project row-scope
    API->>WF: apply transition "Approve"
    WF->>WF: role gate + SoD (approver ≠ requester)
    WF->>Doc: Pending → Approved (submit)
    Doc->>Doc: stamp approved_by
    Note over Doc,Ledger: consumption accrues to the<br/>memo fuel ledger — never a GL Entry
```

### Backend surfaces

All business logic lives on the server across three surfaces:

- **Document events** — `validate` / `on_submit` / `on_cancel` controllers wired in `hooks.py` (`doc_events`) on submittable transactions.
- **Scheduled jobs** — `scheduler_events` registers **17 daily, 4 weekly, 2 monthly** jobs across Habitat and Salis (cost accrual, occupancy sync, compliance and expiry watches, fuel/rental accrual, monthly reconciliations). Each paginates its source in 500-row batches and isolates per-row failures so one bad record never aborts a run.
- **On-demand actions** — whitelisted form buttons: `generate_rooms_and_beds`, `generate_safety_setup`, `mark_received`.

Operational alerting uses native Frappe primitives — Calendar views, Kanban boards, Assignment Rules, Notifications with Email Templates, Auto Email Reports, and ToDo follow-ups — all **disabled by default**, so automation is an explicit operator choice. Technical exceptions go to the standard Error Log and Scheduled Job Log.

## Data integrity: the no-GL boundary

Apex **never** writes GL Entries, Payment Entries, or ERPNext Stock Ledger Entries. Every operational write resolves to a module-owned memo record; the General Ledger sits on the far side of a line nothing crosses automatically.

```mermaid
flowchart LR
    subgraph Ops ["Operational writes (automatic)"]
        direction TB
        COST["Cost allocation ·<br/>utility & work-order cost"]:::engine
        STK["Custody / material movement"]:::engine
        MOVE["Movement cost & recovery"]:::engine
    end

    subgraph Memo ["Memo truth (read-only, reversible · no GL)"]
        direction TB
        AL[("Accommodation Ledger")]:::sink
        SL[("Stock Ledger — signed-qty")]:::sink
        ML[("Movement cost + Payment Request")]:::sink
    end

    subgraph GL ["ERPNext posting (human, opt-in)"]
        direction TB
        BAR{{"the boundary —<br/>nothing crosses automatically"}}:::gate
        GLE["GL Entry · Payment Entry ·<br/>Stock Ledger Entry"]:::ext
        ADD["Additional Salary (HRMS)<br/>draft · only if enabled"]:::ext
    end

    COST ==> AL
    STK ==> SL
    MOVE ==> ML
    AL -. never .-x BAR
    SL -. never .-x BAR
    ML -. never .-x BAR
    BAR -. blocks .- GLE
    STK -. custody damage, gated .-> ADD

    classDef engine fill:#dcfce7,stroke:#166534,color:#166534;
    classDef sink fill:#f1f5f9,stroke:#475569,color:#334155,stroke-dasharray:4 3;
    classDef gate fill:#fef9c3,stroke:#854d0e,color:#854d0e;
    classDef ext fill:#fff7ed,stroke:#9a3412,color:#7c2d12,stroke-dasharray:4 3;
```

Two memo ledgers carry all operational truth. The **Accommodation Ledger** records every operational cost in `posting_mode = "Operational Memo"` (`on_submit` posts, `before_cancel` posts the reversal). The **Accommodation Stock Ledger** is a read-only, signed-quantity ledger for the internal store, written only through helper functions and reversed by a negative mirror row; on-hand balance is `sum(qty where is_cancelled = 0)`. The single financial-posting exception is a draft HRMS *Additional Salary* deduction for custody damage, which fires only when enabled in Habitat Settings.

## Roles and bootstrap

An idempotent `after_install` bootstrap (safe to re-run) seeds four custom roles — **Accommodation Manager**, **Resident Supervisor**, **Finance Manager**, **Internal Auditor** — plus three role profiles, and the custody, maintenance-material, and safety-task catalogs.

## Localization

The desk is delivered fully in Arabic through Frappe translation files (`apex_habitat/translations/ar.csv`). The driver portal stays English-first for a multinational workforce, with an in-portal English/Arabic toggle.

## Install

Apex installs like any standard Frappe app:

```bash
bench get-app apex_habitat
bench --site <site> install-app apex_habitat
bench --site <site> migrate
```

Requires Frappe, ERPNext, and HRMS on v15 (declared via `required_apps`), Python 3.10+, and MariaDB 10.6+. Installation runs the idempotent `after_install` bootstrap.

## License

MIT. Published by AFMCO Support Services Co. Ltd.
