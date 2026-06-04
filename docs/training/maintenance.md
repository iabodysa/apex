# 4. Maintenance

[← Back to index](README.md)

From a request, to an inspection, to a work order — plus subcontractor service
coverage.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor | Resident Request Coordinator | Maintenance Technician | Maintenance Manager | All (any logged-in user) |
|---------|----------------------|---------------------|------------------------------|------------------------|---------------------|--------------------------|
| **Maintenance Request** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit | Read, Write, Create, Submit | Read | — | Create (Read own only) |
| **Maintenance Inspection Report** *(submittable)* | Read, Write, Create, Submit | — | — | — | — | — |
| **Maintenance Work Order** *(submittable)* | — | — | — | **Read, Write** | — | — |
| Maintenance Material / Material Template (masters) | Read, Write, Create | — | — | — | **Read, Write, Create** | — |
| Subcontractor Service Contract / Order | Read, Write, Create | Read | — | — | — | — |

> **Universal intake (most important behaviour):** any logged-in user can raise a
> **Maintenance Request** via the built-in **All** role — they hold **Create**, and
> **Read** only on the rows they own. A server hook
> (`habitat/permissions.py` — `maintenance_request_has_permission` /
> `maintenance_request_query`) widens that read so the **assigned technician** can
> also see a ticket, while still hiding every other user's tickets. Oversight roles
> (System Manager, Accommodation Manager, Resident Supervisor, Resident Request
> Coordinator) see all requests.

> **Maintenance Manager** is an ERPNext-supplied role (not created by Apex). When
> present, it holds Read/Write/Create on the maintenance material masters only.

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
- **Roles:** Manager only.
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
2. **Inspect.** The Manager records a **Maintenance Inspection Report** to scope
   the job and material needs.
3. **Work order.** A **Maintenance Work Order** is issued against the request and
   worked by the **Maintenance Technician** (who holds Read/Write on it). A daily
   escalation job surfaces requests left open too long.

> Trainees should know that **any logged-in user** can raise a Maintenance Request
> and will see only their own; the assigned **Maintenance Technician** sees the
> ticket they are working. The **My Work** workspace and **Action Inbox** desk page
> are the personal home for these. See [Settings & Desk Pages](settings.md).

_[screenshot: Maintenance Request lifecycle]_
