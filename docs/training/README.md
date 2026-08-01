# Apex Training Guide

A practical, role-by-role guide to using **Apex** — the AFMCO workforce
operations suite. `apex/modules.txt` declares **four** names — three functional
modules plus a shared settings layer, one per bullet below:

- **Habitat** — accommodation, custody, safety, maintenance, and facility costs.
- **Salis** — movement and fleet: vehicles, drivers, fuel, dispatch, rentals,
  plus the portals for **Drivers** (`/driver`), **Workers / Masar** (`/masar`),
  **employees** (`/fleet`), **fleet supervisors** (`/fleet-os`), and **route
  supervisors** (`/masar-supervisor`).
- **Logistay** — workforce and telecom operations: freelancers, temporary
  workers, telecom contracts, SIM inventory and custody, billing documents, and
  the **Telecom Control** desk. It ships no workspace of its own; its reports,
  cards, and desk are hosted on the **Custody** workspace. The SIM records
  (`SIM Card`, `SIM Custody Assignment`) belong to this module and are reached
  through **Custody**. Logistay has no training page yet, and the Custody page
  below does not cover it.
- **Apex Core** — shared configuration (Habitat / Salis / Integration settings).

This guide explains, per functional area, **what each record is for**, **who can
do what** (roles and permissions), the **key fields**, and the **typical
workflow** an operator follows.

_[screenshot: Apex desk — module cards for Habitat and Salis]_

---

## Where the permissions are

Every DocPerm row apex ships is listed once in the
[permissions reference](../reference/permissions.md), generated from the shipped
DocType JSON. Each page below links into it instead of repeating a matrix.

The rights it names are the standard Frappe document rights:

- **Submit** freezes a document as an official record.
- **Cancel** reverses a submitted record (and its side effects).
- **Delete** is reserved for cleanup of unsubmitted drafts.

> A DocPerm row is the widest a role can act. A workflow, a permlevel and the
> row-scope rules below all narrow it further.

---

## Roles at a glance

| Role | Module | Typical user |
|------|--------|--------------|
| **Accommodation Manager** | Habitat | Owns housing, custody, safety, and license records |
| **Resident Supervisor** | Habitat | On-site supervisor; raises and executes day-to-day records (building-scoped) |
| **Maintenance Technician** | Habitat | Field technician; reads requests and works **Maintenance Work Orders** |
| **Cleaning Supervisor** | Habitat | Records housekeeping on the **Cleaning Log** |
| **Safety Officer** | Habitat | Field safety operator; records inspections, executions, and incidents |
| **Resident Request Coordinator** | Habitat | Triages resident requests and raises/submits maintenance requests |
| **Finance Manager** | Both | Central finance control; approves payments, reconciles costs |
| **Internal Auditor** | Both | Read-only oversight across all records |
| **Fleet Manager** | Salis | Owns the fleet; unscoped across all projects |
| **Fleet Project Manager** | Salis | Manages vehicles/drivers for assigned projects only |
| **Fleet Supervisor** | Salis | Field supervisor; creates operational records |
| **Government Relations Officer** | Salis | Compliance notification recipient + Compliance workspace viewer (no record-edit rights). It holds Read, Report, and Export on five vehicle and driver compliance records and on three registers, and is granted on the **Salis** root as well as on **Compliance and Rentals** |
| **Driver** | Salis | Field driver; uses the mobile Driver Portal only. The role has `desk_access = 0` and an owner-only permission set on five Salis DocTypes — it never opens the desk |

> **Maintenance Manager** is an ERPNext-supplied role. Apex neither creates it nor
> grants it anything — no shipped DocType names it. Read/Write/Create on the
> maintenance material masters (Maintenance Material, Maintenance Material
> Template) belongs to **Accommodation Manager** and **Maintenance Technician**.

> **Universal Maintenance Request intake:** *any* logged-in user (the built-in
> **All** role) can raise a **Maintenance Request** — they hold Create, and Read
> only on rows they own. A server hook (`habitat/permissions.py`) extends that to
> also let the assigned technician see a ticket, while hiding everyone else's. See
> [Maintenance](maintenance.md).

> **Project scoping (Salis):** Fleet Project Managers and Supervisors see only their permitted projects. Oversight roles (Fleet Manager, Finance Manager, Internal Auditor, Government Relations Officer) see all. Grant access via a *User Permission* on **Project**. The oversight set is `UNSCOPED_ROLES` in `apex/salis/permissions.py`; a role that is neither oversight nor project-granted would be shown lists that can only return no rows, so `apex/salis/test_scope_role_partition.py` fails the build on one.

> **Building scoping (Habitat):** a **Resident Supervisor** is scoped to his building(s) via a *User Permission* on **Building** — that is the DocType name; there is no `Accommodation Building`. The scope is broad, not a short list: `apex/hooks.py` wires a building check onto 28 DocTypes, covering assignment, custody, cleaning, safety, maintenance, rooms and beds, so read it as the default for any building-bearing record. The oversight roles (Accommodation Manager, Finance Manager, Internal Auditor) are unscoped; the set is `HOUSING_UNSCOPED_ROLES` in `apex/habitat/permissions.py`.

---

## Contents

### Habitat
1. [Accommodation](accommodation.md) — sites, buildings, rooms, beds, assignment, checkout, resident requests
2. [Custody](custody.md) — articles issued to residents/staff, returns, damage
3. [Safety](safety.md) — inspections, task catalog/execution, building licenses
4. [Maintenance](maintenance.md) — requests, inspections, work orders
5. [Costs (Facilities & Utilities)](costs.md) — utility accounts, bills, cost allocation

### Salis (Movement & Fleet)
6. [Fleet & Compliance](fleet-movement.md) — vehicles, drivers, dispatch, transport, compliance
7. [Fuel](fuel.md) — quotas, requests, claims, exceptions
8. [Rentals](rentals.md) — rental offices, accrual, settlement
9. [Payments & Approvals](compliance.md) — segregation of duties at the finance boundary

> Salis is organised as a top-level **Salis** workspace with **two** child
> workspaces — **Fleet** and **Compliance and Rentals** — not a single flat area.
> Movement lives on the Salis root itself.

### Portals

Apex serves **seven** portal routes. Their audiences and authentication paths
are listed once in [Served portal routes](../../README.md#served-portal-routes).

10. [Driver & Worker Portals](portals-masar-driver.md) — mobile self-service (`/driver`, `/masar`)

> The **five** session-gated operator portals — `/fleet` (employee
> self-service), `/fleet-os` (fleet supervisor board), `/housing`, `/safety`,
> and `/masar-supervisor` (route supervisor) — do not yet have training pages.
> Until they do, use the route reference above for their audience and access
> rules.

### Shared
11. [Settings & Desk Pages](settings.md) — Apex Core settings, operational desk consoles
12. [Background Jobs](settings.md#background-jobs) — what runs automatically

> **Action Inbox** is the personal worklist. It is a shortcut on both the Habitat and the Salis workspace, open to every user with no role filter. The former **My Work** and **Launchpad** landing workspaces were retired and are removed on migrate by `apex/patches/v2_0/remove_kernel_landing_workspaces.py`. See [Settings & Desk Pages](settings.md).

---

> **Trainer note:** Each area page is self-contained and a few screens long.
> Print or share individual pages with the team that owns that area.
