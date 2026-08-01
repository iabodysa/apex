# 3. Safety

[← Back to index](README.md)

Recurring inspections, the safety-task catalog/execution loop, and building
licenses.

---

## Permissions

The exact grants for these records are in the [permissions reference](../reference/permissions.md#habitat), generated from the shipped DocPerm JSON.

> The **Safety Officer** can raise and edit a **Building License** — it is not a
> Manager-only record — but only the Accommodation Manager submits, cancels, or
> amends one.

> **Internal Auditor** holds read-only oversight (Read, Report) on **Safety
> Incident**. The other safety records grant it nothing.

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

### Safety Incident *(submittable)*
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
3. **Incidents.** Any incident is logged on **Safety Incident** and
   submitted.
4. **Licenses.** Building licenses are tracked on **Building License**; a daily
   scheduled job flags upcoming expiries so the Manager can renew in time.
5. **Compliance scan.** A **daily** job flags overdue Scheduled Task Instances,
   escalates the High and Critical ones with an Operations Alert and a
   notification to the Safety Officer, and flags active buildings with no recent
   safety round. A second **daily** job flags Audit Remediation Plans past their
   remediation deadline.
6. **Weekly coverage gate.** Separately, a **weekly** job checks that every
   active building was covered by a submitted weekly Safety Round that week and
   raises an alert for the buildings that were not.

_[screenshot: Safety Inspection Report findings grid]_
_[screenshot: Safety Map desk page]_

> A **Safety Map** desk page visualises building/task status. See
> [Settings & Desk Pages](settings.md#desk-pages-operational-consoles).
