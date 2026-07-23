# 7. Fuel (Salis)

[← Back to index](README.md)

Quotas, requests, claims, and exception handling. Movement and finance are
deliberately split across the claim lifecycle.

---

## Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| **Fuel Quota** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Request** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Claim** *(workflow)* | Full | Read, Write, Create | Read, Write, Create | Read, Write |
| **Fuel Exception Case** *(workflow)* | Full | scoped | scoped | Read |
| Fuel Platform (master) | Read, Write, Create | Read | Read | Read |

---

## DocTypes in this area

### Fuel Quota *(submittable)*
- **Purpose:** the fuel allowance per vehicle/project for a period.
- **Key fields:** vehicle/project, period, quota amount.

### Fuel Request *(submittable)*
- **Purpose:** a request to draw fuel against a vehicle.
- **Source:** a supervisor, or a driver from the Driver Portal.
- **On submit:** consumes quota.

### Fuel Claim *(workflow)*
- **Purpose:** reconciles requested vs. actual fuel cost.
- **Workflow states:** Draft → *Submitted to Movement* → *Reconciled* /
  *Disputed* → *Approved* → *Closed*.
- **Roles:** Finance Manager has write to reconcile; movement and finance are
  deliberately split.

### Fuel Exception Case *(workflow)*
- **Purpose:** captures anomalies (e.g. un-reverted top-ups) for follow-up.

### Fuel Platform (master)
- **Purpose:** the fuel card/platform/station definitions.

---

## Basic workflow

1. **Set quotas.** Fleet Manager/PM define **Fuel Quota** per vehicle/project.
2. **Request fuel.** A supervisor (or a driver from the portal) raises a **Fuel
   Request** against the vehicle; it is submitted and consumes quota.
3. **Claim & reconcile.** **Fuel Claim** runs its workflow; Finance Manager
   reconciles. Movement and finance are kept separate.
4. **Exceptions.** Anomalies become **Fuel Exception Cases**; daily jobs watch for
   overdue requests and un-reverted top-ups. Monthly fuel reconciliation runs
   automatically.

_[screenshot: Fuel Console]_
_[screenshot: Fuel Approval Console desk page]_

> A **Fuel Approval Console** desk page accelerates claim review. See
> [Settings & Desk Pages](settings.md#desk-pages).
