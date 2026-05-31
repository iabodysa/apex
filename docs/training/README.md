# Apex Training Guide

A practical, role-by-role guide to using **Apex** — the AFMCO workforce
operations suite. Apex hosts two functional modules plus a shared settings layer:

- **Habitat** — accommodation, custody, safety, maintenance, and facility costs.
- **Salis** — movement and fleet: vehicles, drivers, fuel, dispatch, rentals,
  plus mobile portals for **Drivers** and **Workers (Masar)**.
- **Apex Core** — shared configuration (Habitat / Salis / Integration settings).

This guide explains, per functional area, **what each record is for**, **who can
do what** (roles and permissions), the **key fields**, and the **typical
workflow** an operator follows.

_[screenshot: Apex desk — module cards for Habitat and Salis]_

---

## How to read the permission tables

Columns are the standard Frappe document rights: **Read**, **Write**, **Create**,
**Submit**, **Cancel**, **Delete**. A blank cell (—) means the role does not hold
that right.

- **Submit** freezes a document as an official record.
- **Cancel** reverses a submitted record (and its side effects).
- **Delete** is reserved for cleanup of unsubmitted drafts.

> **System Manager** always holds full rights on every DocType and is omitted
> from the per-area tables to keep them focused on operational roles.

---

## Roles at a glance

| Role | Module | Typical user |
|------|--------|--------------|
| **Accommodation Manager** | Habitat | Owns housing, custody, safety, and license records |
| **Resident Supervisor** | Habitat | On-site supervisor; raises and executes day-to-day records |
| **Finance Manager** | Both | Central finance control; approves payments, reconciles costs |
| **Internal Auditor** | Both | Read-only oversight across all records |
| **Fleet Manager** | Salis | Owns the fleet; unscoped across all projects |
| **Fleet Project Manager** | Salis | Manages vehicles/drivers for assigned projects only |
| **Fleet Supervisor** | Salis | Field supervisor; creates operational records |
| **Government Relations Officer** | Salis | Handles sponsorship / compliance casework |
| **Driver** | Salis | Field driver; uses the mobile Driver Portal, minimal desk read |

> **Project scoping (Salis):** Fleet Project Managers and Fleet Supervisors only
> see records for the **Projects** they hold a *User Permission* for. Oversight
> roles — System Manager, Fleet Manager, Internal Auditor, and Finance Manager —
> see **all** projects. Grant a project to a supervisor by adding a *User
> Permission* (allow **Project**) on their user.

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

### Portals
10. [Driver & Worker Portals](portals-masar-driver.md) — mobile self-service (`/driver`, `/masar`)

### Shared
11. [Settings & Desk Pages](settings.md) — Apex Core settings, operational desk consoles
12. [Background Jobs](settings.md#background-jobs) — what runs automatically

---

> **Trainer note:** Each area page is self-contained and a few screens long.
> Print or share individual pages with the team that owns that area.
