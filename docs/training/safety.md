# 3. Safety

[← Back to index](README.md)

Recurring inspections, the safety-task catalog/execution loop, and building
licenses.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| Safety Task Catalog (master) | Read, Write, Create | Read |
| **Safety Inspection Report** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit |
| **Safety Task Execution** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit |
| **Habitat Safety Incident** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit |
| **Building License** *(submittable)* | Read, Write, Create, Submit, Cancel | Read |

---

## DocTypes in this area

### Safety Task Catalog (master)
- **Purpose:** the library of recurring safety checks.
- **Key fields:** task name, frequency, applicable building scope.

### Safety Task Execution *(submittable)*
- **Purpose:** records one performance of a catalogued task.
- **Key fields:** task, building, executed-by, result, date.

### Safety Inspection Report *(submittable)*
- **Purpose:** a structured site inspection with a findings grid.
- **Key fields:** building, inspector, findings (severity, action, status).

### Habitat Safety Incident *(submittable)*
- **Purpose:** records an actual safety incident/near-miss.
- **Key fields:** date, location, severity, description, corrective action.

### Building License *(submittable)*
- **Purpose:** tracks regulatory licenses per building and their expiry.
- **Key fields:** license type, building, issue/expiry dates.
- **Automation:** a daily job flags upcoming expiries.

---

## Basic workflow

1. **Catalog tasks.** The Manager maintains the **Safety Task Catalog**.
2. **Execute.** A supervisor records a **Safety Task Execution** or a **Safety
   Inspection Report** in the field and **Submits** it as the official record.
3. **Incidents.** Any incident is logged on **Habitat Safety Incident** and
   submitted.
4. **Licenses.** Building licenses are tracked on **Building License**; a daily
   scheduled job flags upcoming expiries so the Manager can renew in time.
5. **Compliance scan.** A weekly job scans for overdue safety tasks and raises
   operational alerts.

_[screenshot: Safety Inspection Report findings grid]_
_[screenshot: Safety Map desk page]_

> A **Safety Map** desk page visualises building/task status. See
> [Settings & Desk Pages](settings.md#desk-pages).
