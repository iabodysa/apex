# Apex

Apex is a Frappe v15 workforce-operations suite for accommodation, movement, fleet, contingent workers, and telecom custody.

It combines native Frappe, ERPNext, and HRMS records with focused workflows, operator desks, mobile portals, and system-written operational ledgers. Financial documents stay inside the native ERPNext and HRMS lifecycle, behind explicit approvals and settings.

## Modules

- **Habitat** — accommodation and facilities: sites, buildings, rooms, beds, arrivals, housing assignments, transfers, checkout, custody, internal stores, maintenance, safety, cleaning, leases, utilities, and operational cost snapshots.
- **Salis** — movement and fleet: vehicles, drivers, transport requests, routes, dispatch, boarding, fuel, rentals, cost recovery, compliance, and mobile operations.
- **Apex Core** — shared settings, first-install setup, role bootstrap, action inbox, permissions, notifications, portal-token security, payment routing, and salary-deduction controls.
- **Logistay** — workforce and telecom operations: freelancers paid through native ERPNext documents, temporary workers who may later be linked to an Employee, telecom contracts, SIM inventory and custody, billing documents, reports, and a focused control desk.

## Architecture

Five views describe the system without tying the documentation to volatile record counts.

### Map 1 — Application architecture

```mermaid
graph TD
    PKG(["Apex<br/>one Frappe app"]):::hub

    subgraph CORE_BOX ["Apex Core — shared kernel"]
        CORE_SET["Settings and setup<br/>company · cost center · policy gates"]:::core
        CORE_SEC["Security and coordination<br/>roles · permissions · tokens · inbox"]:::core
    end

    subgraph HAB_BOX ["Habitat — accommodation and facilities"]
        HAB_SPACE["Space and residency<br/>Site · Building · Room · Bed"]:::hab
        HAB_OPS["Facilities operations<br/>Custody · Store · Maintenance · Safety"]:::hab
        HAB_COST["Contracts and controls<br/>Lease · Utility · Ledger · Snapshot"]:::hab
    end

    subgraph SAL_BOX ["Salis — movement and fleet"]
        SAL_MOVE["Movement<br/>Request · Route · Dispatch · Boarding"]:::sal
        SAL_FLEET["Fleet<br/>Vehicle · Driver · Fuel · Rental"]:::sal
        SAL_CTRL["Operational controls<br/>Compliance · Recovery · Settlement"]:::sal
    end

    subgraph EXT_BOX ["Logistay — workforce and telecom operations"]
        LOG_PEOPLE["People<br/>Freelancer · Temporary Worker"]:::ext
        LOG_TELECOM["Telecom<br/>Contract · SIM · Custody · Billing"]:::ext
    end

    subgraph PLATFORM ["Required platform"]
        FRP["Frappe v15<br/>auth · ORM · Workflow · scheduler"]:::plat
        ERP["ERPNext v15<br/>Company · Project · Cost Center · Finance"]:::plat
        HRMS["HRMS v15<br/>Employee · Payroll"]:::plat
    end

    PKG --> CORE_BOX
    PKG --> HAB_BOX
    PKG --> SAL_BOX
    PKG --> EXT_BOX
    CORE_BOX --> PLATFORM
    HAB_BOX --> PLATFORM
    SAL_BOX --> PLATFORM
    EXT_BOX --> PLATFORM

    classDef hub  fill:#1e3a8a,stroke:#1e3a8a,color:#fff;
    classDef core fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;
    classDef hab  fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef sal  fill:#dcfce7,stroke:#166534,color:#166534;
    classDef ext  fill:#fff7ed,stroke:#9a3412,color:#7c2d12;
    classDef plat fill:#f1f5f9,stroke:#475569,color:#334155;
```

Apex Core provides the shared controls; each business module owns its operational records and uses native platform services where they fit.

### Map 2 — Accommodation lifecycle

```mermaid
stateDiagram-v2
    direction LR

    state "Space Setup" as SETUP {
        [*] --> Site
        Site --> Building
        Building --> Room
        Room --> Bed
    }

    state "Active Stay" as ACTIVE {
        Arrival --> Assignment
        Assignment --> Transfer
        Transfer --> Assignment
        Assignment --> DailyOperations
    }

    state "Closeout" as CLOSEOUT {
        Checkout --> CustodyReturn
        CustodyReturn --> Closed
    }

    SETUP --> Arrival : capacity is ready
    ACTIVE --> Checkout : stay ends
    Closed --> [*] : bed becomes available

    note right of DailyOperations
        Safety, cleaning, maintenance,
        custody, utilities, and snapshots.
    end note

    note right of CustodyReturn
        Damage and missing items follow
        a controlled review path.
    end note
```

The resident journey shares one spatial model and one controlled path from arrival to release of the bed.

### Map 3 — Interface and authorization flow

```mermaid
flowchart LR
    subgraph USERS ["Users"]
        DESK_USER["Desk operator"]:::actor
        MOBILE_USER["Worker or driver"]:::actor
        TEAM_USER["Field supervisor"]:::actor
    end

    subgraph UI ["Purpose-built interfaces"]
        DESK["Workspaces and Desk pages<br/>My Work · Action Inbox · Control desks"]:::ui
        PWA["Worker and driver PWA"]:::ui
        PORTALS["Housing · Safety · Fleet · Masar portals"]:::ui
    end

    subgraph ID ["Identity"]
        SESSION["Frappe session"]:::api
        TOKEN["Scoped personal token"]:::api
    end

    API["Whitelisted controllers and document actions"]:::data

    subgraph GUARDS ["Server-side guards"]
        PERM["DocPerm · roles · User Permission"]:::guard
        SCOPE["row scope · ownership · workflow state"]:::guard
        LIFE["submit/cancel and token lifecycle guards"]:::guard
    end

    STORE[("DocTypes · ledgers · snapshots")]:::store
    LIVE["Realtime status and notifications"]:::live

    DESK_USER --> DESK --> SESSION
    MOBILE_USER --> PWA --> TOKEN
    TEAM_USER --> PORTALS --> SESSION
    SESSION --> API
    TOKEN --> API
    API --> GUARDS
    GUARDS --> STORE
    STORE --> LIVE
    LIVE --> DESK
    LIVE --> PWA
    LIVE --> PORTALS

    classDef actor fill:#fff7ed,stroke:#9a3412,color:#7c2d12;
    classDef ui    fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef api   fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;
    classDef data  fill:#fef9c3,stroke:#854d0e,color:#854d0e;
    classDef guard fill:#dcfce7,stroke:#166534,color:#166534;
    classDef store fill:#f1f5f9,stroke:#475569,color:#334155;
    classDef live  fill:#ecfeff,stroke:#0e7490,color:#155e75;
```

The interface changes by role, but identity, authorization, workflow checks, and data scope remain server-side.

### Map 4 — Workspace navigation

```mermaid
graph LR
    LP(["Launchpad<br/>shared entry point"]):::launch
    MW["My Work<br/>personal queue"]:::universal
    BE["Backend Engines<br/>system-written records"]:::restricted

    subgraph HAB_NAV ["Habitat"]
        HAB["Habitat"]:::hub_ws
        HOUSING["Housing"]:::ws
        SAFETY["Safety"]:::ws
        CUSTODY["Custody"]:::ws
        COSTS["Costs and Leasing"]:::ws
    end

    subgraph SAL_NAV ["Salis"]
        SALIS["Salis"]:::sal_ws
        MASAR["Masar"]:::sal_child
        FLEET["Fleet"]:::sal_child
        COMP["Compliance and Rentals"]:::sal_child
    end

    LOG["Logistay<br/>workforce · telecom"]:::log_ws

    LP --> MW
    LP --> HAB
    LP --> SALIS
    LP --> LOG
    LP -. "System Manager" .-> BE

    HAB --> HOUSING
    HAB --> SAFETY
    HAB --> CUSTODY
    HAB --> COSTS

    SALIS --> MASAR
    SALIS --> FLEET
    SALIS --> COMP

    classDef universal  fill:#1e3a8a,stroke:#1e3a8a,color:#fff;
    classDef launch     fill:#5b21b6,stroke:#5b21b6,color:#fff;
    classDef restricted fill:#f1f5f9,stroke:#475569,color:#334155,stroke-dasharray:4 3;
    classDef hub_ws     fill:#1d4ed8,stroke:#1d4ed8,color:#fff;
    classDef ws         fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef sal_ws     fill:#166534,stroke:#166534,color:#fff;
    classDef sal_child  fill:#dcfce7,stroke:#166534,color:#166534;
    classDef log_ws     fill:#9a3412,stroke:#9a3412,color:#fff;
```

Launchpad connects the operating areas. My Work remains personal, while Backend Engines is limited to System Manager because its ledgers and snapshots are system-written and read-only.

## Backend surfaces

- **Document lifecycle** — validation, workflow, submission, cancellation, and reversal rules live in server controllers and hooks.
- **Scheduled engines** — recurring occupancy, cost, compliance, expiry, fuel, rental, reconciliation, and notification work runs through the Frappe scheduler.
- **Operator desks** — focused pages support arrivals, front desk, custody, safety, transfers, fleet control, dispatch, fuel approval, and telecom control.
- **Operational records** — ledgers and historical snapshots are written by the system, not entered or edited by operators.
- **Native coordination** — assignments, notifications, reports, list views, calendars, workflows, and error logs use Frappe primitives.

## Financial boundary

Operational engines do not write directly to the General Ledger. When a process needs procurement, payment, or payroll action, Apex routes it to a native ERPNext or HRMS document with its own permission, approval, validation, and submission lifecycle.

```mermaid
flowchart LR
    EVENT["Operational event or scheduled job"]:::engine

    subgraph MEMO ["Operational truth"]
        LEDGER[("System-written ledger")]:::sink
        SNAP[("Historical snapshot")]:::sink
    end

    APPROVED["Approved business request"]:::request
    ROUTE{"Policy and finance gates"}:::gate

    subgraph NATIVE ["Native ERPNext and HRMS documents"]
        DRAFT["Draft document<br/>Payment Request · Payment Entry<br/>Material Request · Additional Salary"]:::native
        SUBMIT["Native validation and submit"]:::native
        EFFECT["Accounting, procurement,<br/>or payroll effect"]:::effect
    end

    EVENT --> LEDGER
    EVENT --> SNAP
    APPROVED --> ROUTE
    ROUTE -- "disabled" --> HOLD["Remain operational or Draft"]:::hold
    ROUTE -- "enabled and authorized" --> DRAFT
    DRAFT --> SUBMIT
    SUBMIT --> EFFECT
    LEDGER -. "no direct GL posting" .-> EFFECT
    SNAP -. "no direct GL posting" .-> EFFECT

    classDef engine  fill:#dcfce7,stroke:#166534,color:#166534;
    classDef sink    fill:#f1f5f9,stroke:#475569,color:#334155,stroke-dasharray:4 3;
    classDef request fill:#dbeafe,stroke:#1e3a8a,color:#1e3a8a;
    classDef gate    fill:#fef9c3,stroke:#854d0e,color:#854d0e;
    classDef native  fill:#ede9fe,stroke:#5b21b6,color:#5b21b6;
    classDef effect  fill:#fff7ed,stroke:#9a3412,color:#7c2d12;
    classDef hold    fill:#f8fafc,stroke:#64748b,color:#475569;
```

Finance and salary-deduction switches are disabled by default. Enabling them does not bypass native ERPNext or HRMS controls.

## Interface layout

Modern interfaces use a conventional source-build-route-test separation:

```text
frontend/      Vue and Vite source applications
apex/public/   compiled browser assets
apex/www/      Frappe routes and authentication bootstrap
e2e/           browser-level tests
```

Desk users work through native workspaces, forms, reports, and operator pages. Mobile users receive smaller role-focused interfaces, including a shared worker and driver PWA with route-specific access.

## Security and integrity

- Roles, document permissions, ownership, building or project scope, and workflow state are enforced on the server.
- Portal tokens are personal and purpose-scoped; they do not grant Desk roles or broader document access.
- Submission and cancellation guards protect workflow-controlled records from bypass.
- Machine-written ledgers and snapshots are read-only to users and isolated in Backend Engines.

## Localization

Source code and metadata are English-first. User-facing Arabic is maintained through Frappe translation files, and supported portals provide an Arabic interface.

## Install

```bash
cd frappe-bench
bench get-app https://github.com/iabodysa/apex.git
bench --site <site> install-app apex
bench --site <site> migrate
```

Apex requires Frappe, ERPNext, and HRMS v15, Python 3.10+, and MariaDB 10.6+. The first-install setup wizard captures the shared company, cost center, portal controls, and approval policies with conservative defaults.

## Documentation

- [Training guide](docs/TRAINING.md)
- [Integration guide](docs/INTEGRATION.md)
- [Workspace design](docs/WORKSPACE-DESIGN.md)

## License

MIT. Published by AFMCO Support Services Co. Ltd.
