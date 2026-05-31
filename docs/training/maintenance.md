# 4. Maintenance

[← Back to index](README.md)

From a request, to an inspection, to a work order — plus subcontractor service
coverage.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| **Maintenance Request** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit |
| **Maintenance Inspection Report** *(submittable)* | Read, Write, Create, Submit | — |
| **Maintenance Work Order** *(submittable)* | *(System Manager only — configure roles before field use)* | — |
| Maintenance Material Template (master) | Read, Write, Create | Read |
| Subcontractor Service Contract / Order | Read, Write, Create | Read |

---

## DocTypes in this area

### Maintenance Request *(submittable)*
- **Purpose:** the entry point for any repair/maintenance need.
- **Source:** raised by a supervisor or by a resident via the request web form.
- **Key fields:** building/room, category, priority, description.

### Maintenance Inspection Report *(submittable)*
- **Purpose:** scopes the job and the materials needed.
- **Roles:** Manager only.
- **Key fields:** linked request, findings, material estimate.

### Maintenance Work Order *(submittable)*
- **Purpose:** the executable job issued against a request.
- **Key fields:** request reference, assignee/subcontractor, materials, status.
- **Note:** ships with System-Manager-only permissions — assign field-staff
  rights during site setup if supervisors will close work orders.

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
3. **Work order.** A **Maintenance Work Order** is issued against the request. A
   daily escalation job surfaces requests left open too long.

> Maintenance Work Order currently ships with System-Manager-only permissions —
> assign the Accommodation Manager / supervisor rights to it during site setup if
> field staff will close work orders.

_[screenshot: Maintenance Request lifecycle]_
