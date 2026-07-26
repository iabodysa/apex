# 11. Settings & Desk Pages

[← Back to index](README.md)

Shared configuration (Apex Core), the operational desk consoles, and the
automated background jobs.

---

## Shared settings

| DocType | Module | Type | Purpose | Who edits |
|---------|--------|------|---------|-----------|
| **Habitat Settings** | Apex Core | Single | Defaults and toggles for the Habitat module (accommodation, custody, safety, maintenance). | System Manager only |
| **Salis Settings** | Apex Core | Single | Defaults and toggles for the Salis module (fleet, fuel, dispatch, rentals). | System Manager / Fleet Manager |
| **Apex Integration Settings** | Apex Core | Single | Configuration for external integrations. | System Manager |
| **Driver Portal Theme** | Salis | Single | Driver/Worker portal appearance (AFMCO / Frappe / Dark + optional brand overrides). | System Manager / Fleet Manager |
| **Masar Worker Token** | Apex Core | Record | Personal access tokens issued to workers for the Masar portal. | System Manager, Accommodation Manager, Resident Supervisor, Fleet Manager, Fleet Project Manager, Fleet Supervisor, HR User |

> **Habitat Settings is System Manager-only.** The Accommodation Manager cannot
> open or change it, despite owning the records it configures.

> **Read-only viewers:** the Accommodation Manager and Fleet Manager can read
> Apex Integration Settings; the Finance Manager and Internal Auditor can read
> Salis Settings; the Fleet Project Manager and Internal Auditor can read the
> Driver Portal Theme.

> **Masar Worker Token is deliberately wide** — seven roles can issue a token,
> because tokens are handed out by whoever onboards the worker. Only the System
> Manager can delete one.

> Settings are **configuration only** — they hold defaults and feature toggles,
> not transactional data. Review them once during setup and when behaviour needs
> to change.

_[screenshot: Habitat Settings]_
_[screenshot: Driver Portal Theme]_

---

<a id="desk-pages"></a>
## Desk pages (operational consoles)

These are purpose-built desk screens that sit on top of the DocTypes for faster
day-to-day work:

Apex ships **eleven** desk pages:

| Page | Module | Roles | Use |
|------|--------|-------|-----|
| **Front Desk** | Habitat | System Manager, Accommodation Manager, Resident Supervisor | Quick resident/accommodation overview and intake. |
| **Arrivals Desk** | Habitat | System Manager, Accommodation Manager, Resident Supervisor | Process incoming residents. |
| **Custody Kiosk** | Habitat | System Manager, Accommodation Manager, Resident Supervisor | Fast custody issue/return at the front desk. |
| **Safety Map** | Habitat | System Manager, Accommodation Manager, Resident Supervisor | Visual building/task safety status. |
| **Room Setup** | Habitat | System Manager, Accommodation Manager | Build and edit the room and bed layout of a building. |
| **Transfer Board** | Habitat | System Manager, Accommodation Manager | Manage room/bed transfers. |
| **Salis Dispatch Board** | Salis | System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor | Plan and monitor dispatch trips. |
| **Fuel Approval Console** | Salis | System Manager, Fleet Manager, Fleet Project Manager, Finance Manager | Review and action fuel claims/requests. |
| **Operations Control** | Salis | System Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor | Fleet operations control console. |
| **Telecom Control** | Logistay | SIM Operations User, System Manager | SIM and telecom contract control console. |
| **Action Inbox** | Apex Core | *(none — every logged-in user)* | Personal cross-module worklist of items awaiting the signed-in user. |

> **Room Setup, Operations Control, and Telecom Control** are shipped pages that
> earlier versions of this guide left out. Telecom Control belongs to the
> **Logistay** module, and `apex/modules.txt` declares **four** names —
> **Habitat**, **Salis**, **Apex Core**, and **Logistay**. The SIM records live
> in Logistay as well; there is no separate SIM Operations module, and
> `SIM Operations User` in the table above is a role, not a module.

_[screenshot: Front Desk page]_
_[screenshot: Salis Dispatch Board]_

---

## Action Inbox — personal worklist

The **Action Inbox** desk page is the personal, cross-module worklist. It has no
role filter, so it is available to **every logged-in user**, and it is reached
from a shortcut on both the **Habitat** and the **Salis** workspace. Use it as the
daily starting point: it surfaces what needs your action across both modules.

> The former **My Work** landing workspace, which carried this shortcut alongside
> the **Launchpad** workspace, was retired during workspace consolidation. Both
> are removed on migrate by
> `apex/patches/v2_0/remove_kernel_landing_workspaces.py`, which also clears any
> user still pinned to one. The three personal Number Cards — **Pending My
> Action**, **Submitted By Me**, and **Approved Last 48h** — still ship under
> `apex/apex_core/number_card/` and can be added to any dashboard or workspace,
> but no shipped workspace places them.

---

<a id="background-jobs"></a>
## Background jobs

These run on a schedule; trainees should know the records they touch may be
created or flagged automatically. The tables below list **every** entry the app
registers — twenty-six daily, five weekly, three monthly, and two on a cron.

### Daily

| Job | Module | What it does |
|-----|--------|--------------|
| Accommodation cost allocation | Habitat | Fans one job out per building and posts the day's cost into the Accommodation Ledger. |
| Building licence expiry check | Habitat | Flags licences approaching expiry. |
| Open maintenance escalation | Habitat | Surfaces maintenance requests left open too long. |
| Lease expiry | Habitat | Flips a lease past its end date to *Expired*. |
| Idle resident aging | Habitat | Accrues days-idle and estimated cost bleed on open idle-resident reports. |
| Consumable custody expiry watch | Habitat | Flags held custody consumables past their per-article lifespan. |
| Scheduled task instance generator | Habitat | Creates the day's Scheduled Task Instances from the templates. |
| Occupancy snapshot | Habitat | Writes a point-in-time occupancy row per building so history survives. |
| Cleaning log generator | Habitat | Creates today's draft Cleaning Log for every active building. |
| Auto-create cleaning logs | Habitat | Second pass creating one draft Cleaning Log per active building that lacks one. |
| Safety task compliance scan | Habitat | Flags overdue Scheduled Task Instances, escalates High/Critical ones, and flags buildings with no recent safety round. |
| Audit remediation deadline watch | Habitat | Flags Audit Remediation Plans past their remediation deadline. |
| Temporary worker linking | Habitat | Links matured Temporary Workers to Employees and expires lapsed ones. |
| Driver licence expiry watch | Salis | Alerts before a driver licence lapses. |
| Idle vehicle watch | Salis | Flags vehicles with no recent movement. |
| Un-reverted top-up watch | Salis | Flags fuel top-ups never reverted. |
| Overdue fuel request watch | Salis | Flags fuel requests left outstanding. |
| Missing attendance watch | Salis | Flags drivers with no attendance recorded. |
| Vehicle compliance expiry watch | Salis | Alerts before insurance/registration/inspection lapses. |
| Workshop overstay watch | Salis | Flags vehicles in the workshop beyond the configured days. |
| Operations alert reconciliation | Salis | Auto-resolves open alerts whose underlying condition no longer holds. |
| Open alerts digest | Salis | Emails each Fleet Supervisor a roll-up of their open alerts. |
| Assigned suspended/lost SIM watch | Logistay | Digests assigned SIMs that are Suspended or Lost to SIM Operations Users. |
| Fuel consumption accrual | Salis | Accrues Fuel Consumption Ledger rows for recent fuel activity. |
| Rental accrual | Salis | Posts one Rental Accrual Ledger memo per in-service rented vehicle. |
| Orphaned workflow action cleanup | Apex Core | Deletes Open Workflow Actions whose document moved on or no longer exists. |

### Weekly

| Job | Module | What it does |
|-----|--------|--------------|
| Occupancy sync | Habitat | Full reconciliation pass correcting room and building occupancy counter drift. |
| Custody digest | Habitat | Emails each building's responsible supervisor a custody roll-up. |
| Safety coverage gate | Habitat | Checks every active building had a submitted weekly Safety Round, and alerts on those that did not. |
| Vehicle utilisation summary | Salis | Summarises vehicle utilisation for the week. |
| Vehicle utilisation snapshot | Salis | Writes a utilisation row per active vehicle over the trailing seven days. |

### Monthly

| Job | Module | What it does |
|-----|--------|--------------|
| Fuel reconciliation | Salis | Reconciles each active Fuel Quota against ledgered consumption for the period. |
| Rental reconciliation | Salis | Flags any Rental Office still carrying unsettled accrual rows. |
| Employee recovery run | Apex Core | Queues this period's installment against every open cost-recovery advance. Ships **off** — a no-op until the Salary Deduction Policy Damage rule is activated. |

### Cron

| Schedule | Job | What it does |
|----------|-----|--------------|
| Every 5 minutes | Auto-confirm claimed boardings | Confirms timed-out worker boarding claims across active dispatch trips. |
| Daily at 23:00 | Purge oversized access logs | Deletes Access Log rows whose payload exceeds the configured byte threshold. The native age-based cleanup never reclaims these. |

> **There is no rent-due job.** Rent payment rows on a lease are maintained by
> hand — see [Costs](costs.md).

Operational anomalies surface as **Operations Alert** records and desk
notifications — review them as part of the daily routine.

_[screenshot: Operations Alert list]_
