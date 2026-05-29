# Apex

**Apex** (package: `apex_habitat`) is a workforce-operations suite built on
Frappe Framework v15, ERPNext, and HRMS. It packages several operational modules
for Abdullah Fahad Al-Mutairi Co. (AFMCO) into a single Frappe application, sharing
one permission model, one set of master data, and one scheduled-automation surface.

The application ships three modules:

- **Habitat** — accommodation and facilities management for worker housing.
- **Salis** — vehicle, movement, and fleet operations.
- **Apex Core** — shared configuration that both functional modules read from.

The codebase is English-first: Python, JavaScript, JSON metadata, fieldnames,
labels, options, and messages are all English, and user-facing translations are
provided through Frappe translation files rather than hard-coded text.

---

## Modules

### Habitat — accommodation & facilities

Habitat runs the estate-to-resident lifecycle for worker housing:

- **Spatial inventory** — sites, buildings, rooms, and beds, with on-demand
  generation of rooms and beds from a building's floor plan.
- **Residency** — assignment, room/bed transfer, and checkout as submittable
  documents, with occupancy counters kept consistent by a weekly reconciliation
  job. Temporary stays carry an expected checkout date and are surfaced on a daily
  watchlist. An Idle Resident Report tracks non-deployed residents through an
  open/acknowledged/resolved flow.
- **Safety & compliance** — a safety task catalog drives scheduled task templates
  and daily task-instance generation, alongside inspection reports and
  building-license expiry tracking.
- **Maintenance** — resident-raised and inspection-raised requests, work orders, a
  maintenance material catalog, subcontractor service contracts and orders, plus
  aging and backlog reporting.
- **Custody & assets** — custody issue, return, and damage assessment; facility
  assets and asset movements; and operational (non-financial) depreciation
  snapshots.
- **Internal store** — each building acts as its own store, backed by a read-only,
  signed-quantity stock ledger that supports reversal and inter-store transfers.
- **Leasing & utilities** — leases, rent schedules, utility accounts and bills,
  and a daily per-resident cost allocation that posts to an operational memo
  ledger for cost accountability and analytics.

Habitat operational costs and stock movements are recorded in purpose-built memo
ledgers used for analytics and cross-charge accountability; these ledgers are
separate from the ERPNext General Ledger, so financial posting stays an explicit,
human decision.

### Salis — movement & fleet

Salis manages vehicles, drivers, and the movement of people and assets:

- **Fleet & drivers** — vehicles, vehicle categories, driver records, vehicle
  handover, driver attendance, and driver clearance.
- **Movement** — transport requests, route plans, dispatch trips, passenger
  manifests, and trip-fulfilment tracking, with a Transport Request web form and a
  dispatch board page for operations.
- **Fuel** — fuel requests, quotas, claims, daily logs, a fuel consumption ledger,
  exception cases, and a fuel approval console, with daily accrual and monthly
  reconciliation jobs.
- **Rentals & cost recovery** — rental offices, rental vehicle movement, rental
  settlements, daily rental accrual, and movement cost transfer/recovery between
  cost centers.
- **Compliance** — vehicle compliance records and expiry watches, sponsorship
  transfer cases, support tickets, and payment requests.

Salis transactions move through **native Frappe Workflows** for review and
approval (transport requests, dispatch trips, fuel requests, fuel claims, fuel
exception cases, rental settlements, driver clearance, sponsorship transfer cases,
support tickets, and payment requests). Access to operational documents is
**project-scoped**: supervisors and project managers see only the projects they
are permitted to, while oversight roles see all. Reports cover fleet registers,
fuel spend and reconciliation, rental cost and variance, transport SLA, vehicle
utilisation, and cost-recovery aging.

### Apex Core — shared configuration

Apex Core holds the cross-module settings that the functional modules read at
runtime: **Habitat Settings** and **Salis Settings** (both single configuration
documents).

---

## Architecture

- **English-first** — all code, metadata, and messages are English; Arabic and
  other languages are delivered only through Frappe translation files.
- **Native Frappe surfaces** — approvals run on Frappe Workflows; alerting uses
  declarative Notifications, Email Templates, and Auto Email Reports; operational
  views use Kanban boards, calendar views, and Assignment Rules. Dashboards and
  number cards summarise each domain. Automation seeds are idempotent and
  existence-guarded, so installs and migrations can be re-run safely.
- **Role-based permissions with project scoping** — custom roles are seeded on
  install, and Salis movement documents apply per-project row-level scoping in
  addition to standard role permissions.
- **Server-side business logic** — document-event controllers implement
  validate/submit/cancel behavior per DocType; scheduled jobs process their source
  records in batches and isolate per-row errors so a single bad record never aborts
  a run. Technical exceptions are recorded in the standard Error Log and Scheduled
  Job Log.

### Scheduled automation

Scheduled jobs are declared in `hooks.py` under `scheduler_events`:

- **17 daily jobs** — Habitat: accommodation cost allocation, building-license
  expiry check, maintenance escalation, lease-expiry watchlist, temporary-stay
  checkout watchlist, idle-resident aging, scheduled-task-instance generation, and
  occupancy snapshot. Salis: driver-license expiry watch, idle-vehicle watch,
  unreverted-topup watch, overdue fuel-request watch, missing-attendance watch,
  vehicle-compliance expiry watch, operations-alert reconciliation, fuel
  consumption accrual, and rental accrual.
- **4 weekly jobs** — Habitat occupancy sync and safety-task compliance scan; Salis
  vehicle-utilization summary and utilisation snapshot.
- **2 monthly jobs** — Habitat rent-due alert and Salis fuel reconciliation.

---

## Install

Apex installs like any standard Frappe app:

```bash
bench get-app apex_habitat <repository-url>
bench --site <your-site> install-app apex_habitat
bench --site <your-site> migrate
```

It requires Frappe, ERPNext, and HRMS on v15 (declared via `required_apps` in
`hooks.py`), Python 3.10+, and MariaDB 10.6+. Installation runs an idempotent
bootstrap that seeds roles, catalogs, notifications, workflows, and dashboards;
re-running it is safe.

---

## Repository

<https://github.com/iabodysa/apex>

---

## License

MIT. Published by Abdullah Fahad Al-Mutairi Co. (AFMCO).

This application is free and open-source. All I ask is that you keep me in your
prayers.
