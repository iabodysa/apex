# 9. Payments & Approvals — Segregation of Duties

[← Back to index](README.md)

Finance-boundary records enforce **maker ≠ checker** at the permission layer, on
top of project scoping.

---

## Permissions

> Note the **asymmetry**: Fleet PM holds **no** permission on Movement Cost
> Recovery, and Fleet Supervisor holds **no** permission on Movement Cost Transfer.

> On **Movement Cost Recovery** the Fleet Supervisor also holds **Submit** — it is
> the one record in this table a supervisor can submit himself.

> **Internal Auditor** holds read-only oversight on all three records.

---

## DocTypes in this area

### Salis Payment Request *(workflow)*
- **Purpose:** requests a payment to a vendor/office/driver.
- **Segregation of duties:** the operator who *created* the request cannot also be
  the Finance Manager who *approves/pays* it. The `payment_sod_has_permission`
  hook blocks the maker from approving their own request, and also project-scopes
  the row. **This is the only SoD written in Python** — but it is not the only
  self-approval block in the app (see below).

### Movement Cost Recovery / Movement Cost Transfer *(workflow)*
- **Purpose:** reallocates movement cost between projects/cost owners.
- **Access:** see the asymmetry note above — Fleet PM has no Recovery perm; Fleet
  Supervisor has no Transfer perm.
- **Both are submittable and both run a shipped Frappe Workflow**, so their
  approval steps are governed by workflow transitions, not by a plain submit.

---

## How segregation of duties works

- **Maker ≠ checker** is enforced in code, not just by convention: even a user who
  holds both roles cannot approve a request they created.
- **Project scoping** is layered underneath — an approver still only sees the
  projects they are permitted to.
- **The native workflow engine blocks self-approval far more widely.** Apex ships
  transitions marked *self-approval not allowed* on Movement Cost Recovery,
  Movement Cost Transfer, Salis Payment Request, Rental Settlement, Fuel Claim,
  Fuel Request, Fuel Exception Case, Transport Request, Vehicle Damage Write-Off,
  Utility Bill Entry, Lease, Custody Damage Assessment, and Subcontractor Service
  Contract. On those steps Frappe itself refuses an approval by the document's
  own author — no Apex code is involved.

_[screenshot: Salis Payment Request approval action]_

> When onboarding a Finance Manager, confirm they do not also hold a creator role on the same project — the SoD guard will block self-approval.
