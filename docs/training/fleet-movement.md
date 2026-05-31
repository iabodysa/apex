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
| **Salis Vehicle** | Full | Read, Write, Create, Submit | Read, Write, Create | — | Read |
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
| **Support Ticket** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create, Submit | Read, Create |

### DocTypes
- **Vehicle Assignment** — binds a vehicle to a driver/project for a period.
- **Transport Request** — captures who needs moving where; runs the *Transport
  Request Workflow* (Draft → approval → fulfilment).
- **Dispatch Trip** — schedules the actual run; the driver sees it in the portal.
- **Route Plan / Route Stop** — groups ordered stops for a trip.
- **Passenger Manifest** — the people carried on a trip.
- **Support Ticket** — field issues; runs the *Support Ticket Workflow*.

### Workflow
1. **Assign a vehicle.** Create a **Vehicle Assignment** binding a vehicle to a
   driver/project; submit it.
2. **Request transport.** A **Transport Request** runs through the native
   workflow rather than a plain submit.
3. **Dispatch.** A **Dispatch Trip** schedules the run; **Route Plan** groups
   stops. The driver sees today's trips in the portal.
4. **Tickets.** Field issues are logged as **Support Tickets**, which follow the
   Support Ticket Workflow to resolution.

_[screenshot: Dispatch Board page]_

> Background jobs in this area: driver-license / vehicle-compliance expiry,
> idle-vehicle, missing-attendance, vehicle-utilisation summary. See
> [Background Jobs](settings.md#background-jobs).
