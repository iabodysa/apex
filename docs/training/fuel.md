# 7. Fuel (Salis)

[← Back to index](README.md)

Quotas, requests, claims, and exception handling. Movement and finance are
deliberately split across the claim lifecycle.

---

## Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| **Fuel Quota** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Request** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Claim** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | Read, Write, Create | Read, Write |
| **Fuel Exception Case** *(workflow)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | Read, Write, Create | Read |
| Fuel Platform (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read |

> **Fuel Platform is not read-only for the project roles.** Both the Fleet Project
> Manager and the Fleet Supervisor can create and edit a platform record; only the
> Fleet Manager can delete one.

> **Row scoping** is layered on top of these rights. A Fleet Project Manager or
> Fleet Supervisor sees only the rows for the projects they are permitted to, on
> every fuel record in this table.

> **Internal Auditor** holds read-only oversight (Read, Report, Export) on all
> five records.

---

## DocTypes in this area

### Fuel Quota *(submittable)*
- **Purpose:** the fuel allowance per vehicle/project for a period.
- **Key fields:** vehicle/project, period, quota amount.

### Fuel Request *(submittable)*
- **Purpose:** a request to draw fuel against a vehicle.
- **Source:** a supervisor, or a driver from the Driver Portal.
- **On submit:** only a **Standard** request that is already *Done* consumes
  quota. A **Top-up** or **Chip** request consumes none — it records a note on the
  vehicle's timeline instead.

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
   Request** against the vehicle and submits it. A Standard request draws down
   quota once it is Done; top-ups and chip actions do not.
3. **Claim & reconcile.** **Fuel Claim** runs its workflow; Finance Manager
   reconciles. Movement and finance are kept separate.
4. **Exceptions.** Anomalies become **Fuel Exception Cases**; daily jobs watch for
   overdue requests and un-reverted top-ups. Monthly fuel reconciliation runs
   automatically.

_[screenshot: Fuel Console]_
_[screenshot: Fuel Approval Console desk page]_

> A **Fuel Approval Console** desk page accelerates claim review. See
> [Settings & Desk Pages](settings.md#desk-pages).
