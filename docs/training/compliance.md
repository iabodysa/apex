# 9. Payments & Approvals — Segregation of Duties

[← Back to index](README.md)

Finance-boundary records enforce **maker ≠ checker** at the permission layer, on
top of project scoping.

---

## Permissions

| DocType | Fleet Manager | Fleet PM | Fleet Supervisor | Finance Manager |
|---------|---------------|----------|------------------|-----------------|
| **Salis Payment Request** *(workflow)* | Full | Read, Write, Create | Read, Write, Create | Read, Write, Submit, Cancel |
| **Movement Cost Recovery** *(submittable)* | Full | — | Read, Write, Create | Read, Write |
| **Movement Cost Transfer** *(submittable)* | Full | Read, Write, Create | — | Read, Write |

> Note the **asymmetry**: Fleet PM holds **no** permission on Movement Cost
> Recovery, and Fleet Supervisor holds **no** permission on Movement Cost Transfer.

---

## DocTypes in this area

### Salis Payment Request *(workflow)*
- **Purpose:** requests a payment to a vendor/office/driver.
- **Segregation of duties:** the operator who *created* the request cannot also be
  the Finance Manager who *approves/pays* it. The `payment_sod_has_permission`
  hook blocks the maker from approving their own request. **This is the only
  code-enforced finance-boundary SoD in the app.**

### Movement Cost Recovery / Movement Cost Transfer *(submittable)*
- **Purpose:** reallocates movement cost between projects/cost owners.
- **Access:** see the asymmetry note above — Fleet PM has no Recovery perm; Fleet
  Supervisor has no Transfer perm.

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
