# 9. Payments & Approvals — Segregation of Duties

[← Back to index](README.md)

Finance-boundary records enforce **maker ≠ checker** at the permission layer, on
top of project scoping.

---

## Permissions

| DocType | Fleet Manager | Fleet PM | Fleet Supervisor | Finance Manager |
|---------|---------------|----------|------------------|-----------------|
| **Salis Payment Request** *(workflow)* | Full | Read, Write, Create | Read, Write, Create | Read, Write, Submit, Cancel |
| **Approval Request** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |
| Movement Cost Recovery / Transfer | Full | Read, Write, Create | Read, Write, Create | Read, Write |

---

## DocTypes in this area

### Salis Payment Request *(workflow)*
- **Purpose:** requests a payment to a vendor/office/driver.
- **Segregation of duties:** the operator who *created* the request cannot also be
  the Finance Manager who *approves/pays* it. The `payment_sod_has_permission`
  hook blocks the maker from approving their own request.

### Approval Request *(workflow)*
- **Purpose:** a generic approval gate for operational decisions.
- **Segregation of duties:** the *approver must differ from the requester*
  (`approval_sod_has_permission`). Project scoping still applies on top of this.

### Movement Cost Recovery / Movement Cost Transfer
- **Purpose:** reallocates movement cost between projects/cost owners.

---

## How segregation of duties works

- **Maker ≠ checker** is enforced in code, not just by convention: even a user who
  holds both roles cannot approve a request they created.
- **Project scoping** is layered underneath — an approver still only sees the
  projects they are permitted to.

_[screenshot: Salis Payment Request approval action]_

> This is the most sensitive permission area. When onboarding a Finance Manager,
> confirm they do **not** also hold a creator role on the same project, or the SoD
> guard will (correctly) block them from approving their own work.
