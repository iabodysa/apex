# 6. Fleet & Compliance (Salis)

[← Back to index](README.md)

> All operational Salis transactions are **project-scoped**. A Fleet Supervisor or
> Fleet Project Manager only sees records for their assigned projects. Always set
> the correct **Project** on a new record.

This page covers fleet masters, compliance, dispatch, and transport.

---

## Fleet masters — Vehicles & Drivers

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver | Finance / Auditor |
|---------|---------------|-----------------------|------------------|--------|-------------------|
| **Salis Vehicle** | Full | Read, Write, Create | Read, Write, Create | — | Read |
| **Salis Driver** | Full | Read, Write, Create, Submit | Read, Write, Create | Read | Read |
| Vehicle Category (master) | Read, Write, Create | Read | Read | — | Read |
| **Salis Vehicle Compliance** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | — | Read |
| **Driver Clearance** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | — | Read |

### DocTypes
- **Salis Vehicle** — the fleet asset: plate, category, compliance docs, status.
- **Salis Driver** — the driver record: license dates, project, linked user.
- **Salis Vehicle Compliance** — insurance/registration/inspection validity.
- **Driver Clearance** — sponsorship/clearance casework (Government Relations).
- **Vehicle Handover** — vehicle hand-over checklist between holders.

### Workflow
1. **Register the fleet.** Fleet Manager/PM create **Salis Vehicle** and **Salis
   Driver** records.
2. **Compliance & licenses.** Daily jobs watch driver-license and
   vehicle-compliance expiries and raise operational alerts before they lapse.
3. **Idle watch.** A daily idle-vehicle job flags vehicles with no recent movement.

_[screenshot: Salis Vehicle record with compliance tab]_

---

## Dispatch & Transport

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver |
|---------|---------------|-----------------------|------------------|--------|
| **Vehicle Assignment** *(submittable)* | Full | Read, Write, Create, Submit, Cancel | Read, Write, Create | — |
| **Transport Request** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create, Submit | — |
| **Dispatch Trip** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read (own, via portal) |
| **Route Plan** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | — |
| **Passenger Manifest** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read (own) |
| **Issue** (field support) | Read, Write | — | Read, Write | Read, Create (own) |

> **Salis Vehicle** is **not a submittable** DocType — there is no Submit action.
> Create the record and save it.

### DocTypes
- **Vehicle Assignment** — binds a vehicle to a driver/project for a period.
- **Transport Request** — captures who needs moving where; runs the *Transport
  Request Workflow* (Draft → approval → fulfilment).
- **Dispatch Trip** — schedules the actual run; the driver sees it in the portal.
- **Route Plan / Route Stop** — groups ordered stops for a trip.
- **Passenger Manifest** — the people carried on a trip.
- **Issue** — field support tickets ride the **native ERPNext Issue** DocType (the
  old "Support Ticket" DocType was retired). A driver-raised Issue is tagged with a
  `custom_driver` field; Apex seeds the Issue Types, Priorities, and a default SLA.
  Apex adds **no** Issue permissions of its own (`apex/salis/custom/issue.json`
  ships an empty `custom_perms`), so desk access to Issue is whatever the platform
  grants. The Driver role holds none: the portal raises and reads a driver's
  tickets on their behalf and refuses any Issue whose `custom_driver` is not the
  resolved driver.

### Workflow
1. **Assign a vehicle.** Create a **Vehicle Assignment** binding a vehicle to a
   driver/project; submit it.
2. **Request transport.** A **Transport Request** runs through the native
   workflow rather than a plain submit.
3. **Dispatch.** A **Dispatch Trip** schedules the run; **Route Plan** groups
   stops. The driver sees today's trips in the portal.
4. **Tickets.** Field issues are logged as native **Issue** records (drivers raise
   them from the Driver Portal; fleet staff resolve them on the desk).

_[screenshot: Dispatch Board page]_

> Background jobs in this area: driver-license / vehicle-compliance expiry,
> idle-vehicle, missing-attendance, vehicle-utilisation summary. See
> [Background Jobs](settings.md#background-jobs).
