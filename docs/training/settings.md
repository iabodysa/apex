# 11. Settings & Desk Pages

[← Back to index](README.md)

Shared configuration (Apex Core), the operational desk consoles, and the
automated background jobs.

---

## Apex Core settings

| DocType | Type | Purpose | Who edits |
|---------|------|---------|-----------|
| **Habitat Settings** | Single | Defaults and toggles for the Habitat module (accommodation, custody, safety, maintenance). | System Manager / Accommodation Manager |
| **Salis Settings** | Single | Defaults and toggles for the Salis module (fleet, fuel, dispatch, rentals). | System Manager / Fleet Manager |
| **Apex Integration Settings** | Single | Configuration for external integrations. | System Manager |
| **Salis Portal Theme** | Single | Driver/Worker portal appearance (AFMCO / Frappe / Dark + optional brand overrides). | System Manager |
| **Masar Worker Token** | Record | Personal access tokens issued to workers for the Masar portal. | System Manager / Fleet Manager |

> Settings are **configuration only** — they hold defaults and feature toggles,
> not transactional data. Review them once during setup and when behaviour needs
> to change.

_[screenshot: Habitat Settings]_
_[screenshot: Salis Portal Theme]_

---

<a id="desk-pages"></a>
## Desk pages (operational consoles)

These are purpose-built desk screens that sit on top of the DocTypes for faster
day-to-day work:

| Page | Module | Use |
|------|--------|-----|
| **Front Desk** | Habitat | Quick resident/accommodation overview and intake. |
| **Custody Kiosk** | Habitat | Fast custody issue/return at the front desk. |
| **Safety Map** | Habitat | Visual building/task safety status. |
| **Transfer Board** | Habitat | Manage room/bed transfers. |
| **Salis Dispatch Board** | Salis | Plan and monitor dispatch trips. |
| **Fuel Approval Console** | Salis | Review and action fuel claims/requests. |

_[screenshot: Front Desk page]_
_[screenshot: Salis Dispatch Board]_

---

<a id="background-jobs"></a>
## Background jobs

These run on a schedule; trainees should know the records they touch may be
created or flagged automatically:

- **Daily:** accommodation cost allocation, license-expiry checks, maintenance
  escalation, lease/temporary-stay watchlists, idle-resident aging,
  scheduled-task generation, occupancy snapshot; Salis driver-license /
  vehicle-compliance expiry, idle-vehicle, un-reverted top-up, overdue-fuel,
  missing-attendance watches, fuel accrual, rental accrual.
- **Weekly:** occupancy sync, safety-task compliance scan, vehicle-utilisation
  summary/snapshot.
- **Monthly:** rent-due alert, fuel reconciliation.

Operational anomalies surface as **Operational Alert** records and desk
notifications — review them as part of the daily routine.

_[screenshot: Operational Alert list]_
