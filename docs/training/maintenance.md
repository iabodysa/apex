# 4. Maintenance

[← Back to index](README.md)

From a request, to an inspection, to a work order — plus subcontractor service
coverage.

---

## Permissions

The **All** column is the built-in Frappe role every logged-in user holds.

| DocType | Accommodation Manager | Resident Supervisor | Resident Request Coordinator | Maintenance Technician | All |
|---------|----------------------|---------------------|------------------------------|------------------------|--------------------------|
| **Maintenance Request** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit | Read, Write, Create, Submit | Read | Read, Create *(own only)* |
| **Maintenance Inspection Report** *(submittable)* | — | — | — | — | — |
| **Maintenance Work Order** *(submittable)* | — | — | — | **Read, Write** | — |
| Maintenance Material (master) | Read, Write, Create | — | — | **Read, Write, Create** | — |
| Maintenance Material Template (master) | Read, Write, Create | — | — | **Read, Write, Create** | — |
| **Subcontractor Service Contract** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | — | — | — | — |
| **Subcontractor Service Order** *(submittable)* | Read, Write, Create, Submit | — | — | — | — |

> **Universal intake:** any logged-in user can raise a **Maintenance Request** and sees only their own. The assigned technician also sees their ticket. Oversight roles see all.

> **There is no Maintenance Manager role in Apex.** The maintenance material
> masters are held by the **Maintenance Technician** — Read, Write, Create —
> alongside the Accommodation Manager. Do not look for a Maintenance Manager
> when assigning material access.

> **Maintenance Inspection Report is System Manager-only.** Its permissions grant
> no operational role anything, so an Accommodation Manager cannot open, create,
> or submit one without an administrator role. Treat the inspection step as
> administrator-run until that changes.

> **Subcontractor records are Accommodation Manager-only.** The Resident
> Supervisor holds nothing on the service contract or the service order.

---

## DocTypes in this area

### Maintenance Request *(submittable)*
- **Purpose:** the entry point for any repair/maintenance need.
- **Source:** raised by **any logged-in user** (universal intake), by a supervisor
  or the **Resident Request Coordinator**, or by a resident via the request web form.
- **Privacy:** a raiser sees only their own requests; the assigned technician also
  sees the ticket assigned to them. Oversight roles see all.
- **Key fields:** building/room, category, priority, description.

### Maintenance Inspection Report *(submittable)*
- **Purpose:** scopes the job and the materials needed.
- **Roles:** System Manager only — no operational maintenance or housing role
  holds any right on it.
- **Key fields:** linked request, findings, material estimate.

### Maintenance Work Order *(submittable)*
- **Purpose:** the executable job issued against a request.
- **Roles:** the **Maintenance Technician** is the work-order operator and holds
  **Read/Write** out of the box — no setup is required to let field staff work
  orders.
- **Key fields:** request reference, assignee/subcontractor, materials, status.

### Subcontractor Service Contract / Service Order
- **Purpose:** records external service providers and the work assigned to them.
- **Related:** Subcontractor Building Coverage maps providers to buildings.

### Maintenance Material Template
- **Purpose:** reusable bills of material for common jobs.

---

## Basic workflow

1. **Raise a request.** A supervisor (or a resident via the request web form)
   creates a **Maintenance Request** and submits it.
2. **Inspect.** A **Maintenance Inspection Report** scopes the job and material
   needs. Only a System Manager can record one today.
3. **Work order.** A **Maintenance Work Order** is issued against the request and
   worked by the **Maintenance Technician** (who holds Read/Write on it). A daily
   escalation job surfaces requests left open too long.

_[screenshot: Maintenance Request lifecycle]_
