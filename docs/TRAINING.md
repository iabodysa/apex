# Apex Training Guide

A practical, role-by-role guide to using **Apex** — the AFMCO workforce operations
suite. Apex hosts two functional modules:

- **Habitat** — accommodation, custody, safety, maintenance, and facility costs.
- **Salis** — movement and fleet: vehicles, drivers, fuel, dispatch, and rentals,
  plus a mobile **Driver Portal**.

This guide explains, for each area, **who can do what** (roles and permissions) and
the **basic workflow** an operator follows. Screens are marked with
`![screenshot: ...]` placeholders where an image should be inserted.

> **How to read the permission tables**
> Columns are the standard Frappe document rights: **Read**, **Write**, **Create**,
> **Submit**, **Cancel**, **Delete**. A blank cell means the role does not hold that
> right. *Submit* freezes a document as an official record; *Cancel* reverses a
> submitted record (and its side effects); *Delete* is reserved for cleanup of
> unsubmitted drafts.
>
> **System Manager** always holds full rights on every DocType below and is omitted
> from the per-area tables to keep them focused on operational roles.

---

## Roles at a glance

| Role | Module | Typical user |
|------|--------|--------------|
| **Accommodation Manager** | Habitat | Owns housing, custody, safety, and license records |
| **Resident Supervisor** | Habitat | On-site supervisor; raises and executes day-to-day records |
| **Finance Manager** | Both | Central finance control; approves payments, reconciles costs |
| **Internal Auditor** | Both | Read-only oversight across all records |
| **Fleet Manager** | Salis | Owns the fleet; unscoped across all projects |
| **Fleet Project Manager** | Salis | Manages vehicles/drivers for assigned projects only |
| **Fleet Supervisor** | Salis | Field supervisor; creates operational records |
| **Government Relations Officer** | Salis | Handles sponsorship / compliance casework |
| **Driver** | Salis | Field driver; uses the mobile Driver Portal, minimal desk read |

> **Project scoping (Salis):** Fleet Project Managers and Fleet Supervisors only
> see records for the **Projects** they hold a *User Permission* for. Oversight
> roles — System Manager, Fleet Manager, Internal Auditor, and Finance Manager —
> see **all** projects. Grant a project to a supervisor by adding a *User
> Permission* (allow **Project**) on their user.

![screenshot: Apex desk — module cards for Habitat and Salis]

---

# HABITAT

## 1. Accommodation

Master data (sites, buildings, rooms, beds) underpins the day-to-day assignment and
checkout records.

### Permissions

| DocType | Accommodation Manager | Resident Supervisor | Finance Manager |
|---------|----------------------|---------------------|-----------------|
| Accommodation Site / Building | Read, Write, Create | Read | — |
| Facility Asset | Read, Write, Create | Read | — |
| **Accommodation Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit | — |
| **Accommodation Checkout** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit | — |
| Accommodation Resident Request | Read, Write, Create | Read, Write, Create | — |

### Basic workflow

1. **Set up masters once.** The Accommodation Manager creates the Site → Building →
   Room → Bed hierarchy. Supervisors have read access so they can pick beds.
2. **Assign a resident.** A supervisor creates an **Accommodation Assignment**,
   selects the employee and an available bed, and **Submits** it. Submission marks
   the bed occupied and posts to the occupancy ledger.
3. **Check out.** When a resident leaves, create an **Accommodation Checkout** and
   **Submit** it to free the bed. Only the Accommodation Manager can **Cancel** a
   submitted assignment or checkout if it was raised in error.
4. **Resident self-service.** Residents scan an **Accommodation QR Location** and
   file an **Accommodation Resident Request** (maintenance, complaint, move). The
   Manager and supervisors triage these from the desk.

![screenshot: Accommodation Assignment form with bed selection]
![screenshot: Resident Request intake via QR web form]

---

## 2. Custody

Tracks articles issued to residents/staff and their return or damage.

### Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| Custody Article (master) | Read, Write, Create, Delete | Read, Write, Create |
| **Custody Issue** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create |
| **Custody Return** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create |
| **Custody Damage Assessment** *(submittable)* | Read, Write, Create, Submit, Cancel | — |

> Note: supervisors can **prepare** custody issues and returns but cannot **submit**
> them — the Accommodation Manager submits, keeping a single point of accountability.

### Basic workflow

1. **Define articles** in the Custody Article master (with category).
2. **Issue.** Create a **Custody Issue**, list the items and the holder, then the
   Manager **Submits** it — the items are now on that person's custody.
3. **Return.** On hand-back, create a **Custody Return** referencing the issue and
   **Submit** it; outstanding custody is reduced.
4. **Damage.** If items come back damaged, the Manager raises a **Custody Damage
   Assessment** and submits it to record the loss (non-financial depreciation feeds
   from here).

![screenshot: Custody Issue with item grid]

---

## 3. Safety

Recurring inspections and the safety-task catalog/execution loop.

### Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| Safety Task Catalog (master) | Read, Write, Create | Read |
| **Safety Inspection Report** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit |
| **Safety Task Execution** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit |
| **Building License** *(submittable)* | Read, Write, Create, Submit, Cancel | Read |

### Basic workflow

1. **Catalog tasks.** The Manager maintains the **Safety Task Catalog** (the library
   of recurring checks).
2. **Execute.** A supervisor records a **Safety Task Execution** or a **Safety
   Inspection Report** in the field and **Submits** it as the official record.
3. **Licenses.** Building licenses are tracked on **Building License**; a daily
   scheduled job flags upcoming expiries so the Manager can renew in time.
4. **Compliance scan.** A weekly job scans for overdue safety tasks and raises
   operational alerts.

![screenshot: Safety Inspection Report findings grid]

---

## 4. Maintenance

From a request, to inspection, to a work order.

### Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| **Maintenance Request** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit |
| **Maintenance Inspection Report** *(submittable)* | Read, Write, Create, Submit | — |
| **Maintenance Work Order** *(submittable)* | *(System Manager only — configure roles before field use)* | — |

### Basic workflow

1. **Raise a request.** A supervisor (or a resident via the request web form)
   creates a **Maintenance Request** and submits it.
2. **Inspect.** The Manager records a **Maintenance Inspection Report** to scope the
   job and material needs.
3. **Work order.** A **Maintenance Work Order** is issued against the request. A
   daily escalation job surfaces requests left open too long.

> Maintenance Work Order currently ships with System-Manager-only permissions —
> assign the Accommodation Manager / supervisor rights to it during site setup if
> field staff will close work orders.

![screenshot: Maintenance Request lifecycle]

---

## 5. Costs (Facilities & Utilities)

Utility bills and accommodation cost allocation.

### Permissions

| DocType | Accommodation Manager | Finance Manager |
|---------|----------------------|-----------------|
| Utility Account (master) | Read, Write, Create | — |
| **Utility Bill Entry** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit, Cancel |

### Basic workflow

1. **Register accounts.** The Manager sets up each **Utility Account** (electricity,
   water, etc.).
2. **Enter bills.** A **Utility Bill Entry** is created per invoice and **Submitted**.
   Finance Manager can submit and **Cancel** entries as the cost-control owner.
3. **Allocate.** A daily job (`daily_accommodation_cost_allocation`) spreads costs to
   the occupancy ledger; monthly rent-due alerts run automatically.

![screenshot: Utility Bill Entry form]

---

# SALIS (Movement & Fleet)

> All operational Salis transactions are **project-scoped**. A Fleet Supervisor or
> Fleet Project Manager only sees records for their assigned projects. Always set
> the correct **Project** on a new record.

## 6. Fleet masters — Vehicles & Drivers

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver | Finance / Auditor |
|---------|---------------|-----------------------|------------------|--------|-------------------|
| **Salis Vehicle** | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | — | Read |
| **Salis Driver** | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read | Read |

### Basic workflow

1. **Register the fleet.** Fleet Manager/PM create **Salis Vehicle** and **Salis
   Driver** records (category, plate, compliance docs, license dates).
2. **Compliance & licenses.** Daily jobs watch driver-license and vehicle-compliance
   expiries and raise operational alerts before they lapse.
3. **Idle watch.** A daily idle-vehicle job flags vehicles with no recent movement.

![screenshot: Salis Vehicle record with compliance tab]

---

## 7. Dispatch & Transport

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver |
|---------|---------------|-----------------------|------------------|--------|
| **Vehicle Assignment** *(submittable)* | Full | Read, Write, Create, Submit, Cancel | Read, Write, Create | — |
| **Transport Request** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create, Submit | — |
| **Dispatch Trip** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read (own, via portal) |
| **Route Plan** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | — |
| **Support Ticket** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create, Submit | Read, Create |

### Basic workflow

1. **Assign a vehicle.** Create a **Vehicle Assignment** binding a vehicle to a
   driver/project; submit it.
2. **Request transport.** A **Transport Request** captures who needs moving where.
   It runs through the native **Transport Request Workflow** (Draft → approval →
   fulfilment) rather than a plain submit.
3. **Dispatch.** A **Dispatch Trip** schedules the actual run; **Route Plan** groups
   stops. The driver sees today's trips in the portal.
4. **Tickets.** Field issues are logged as **Support Tickets**, which follow the
   Support Ticket Workflow to resolution.

![screenshot: Dispatch Board page]

---

## 8. Fuel

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| **Fuel Request** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Quota** *(submittable)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Claim** *(workflow)* | Full | Read, Write, Create | Read, Write, Create | Read, Write |
| **Fuel Exception Case** *(workflow)* | Full | scoped | scoped | Read |

### Basic workflow

1. **Set quotas.** Fleet Manager/PM define **Fuel Quota** per vehicle/project.
2. **Request fuel.** A supervisor (or a driver from the portal) raises a **Fuel
   Request** against the vehicle; it is submitted and consumes quota.
3. **Claim & reconcile.** **Fuel Claim** runs the *Fuel Claim Workflow*: Draft →
   *Submitted to Movement* → *Reconciled* / *Disputed* → *Approved* → *Closed*.
   Finance Manager has write to reconcile; movement and finance are deliberately
   split.
4. **Exceptions.** Anomalies (e.g. un-reverted top-ups) become **Fuel Exception
   Cases**; daily jobs watch for overdue requests and un-reverted top-ups. Monthly
   fuel reconciliation runs automatically.

![screenshot: Fuel Console]

---

## 9. Rentals

### Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| Rental Office (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read |
| **Rental Settlement** *(workflow)* | Full | Read, Write, Create | — | Read, Write |

### Basic workflow

1. **Register offices** providing rented vehicles.
2. **Accrue.** A daily rental-accrual job posts rental cost to the accrual ledger.
3. **Settle.** A **Rental Settlement** runs the *Rental Settlement Workflow*; Finance
   Manager reviews and writes the settlement figures; Fleet Manager closes it.

![screenshot: Rental Settlement form]

---

## 10. Payments & Approvals (Segregation of Duties)

Finance-boundary records enforce **maker ≠ checker** at the permission layer.

### Permissions

| DocType | Fleet Manager | Fleet PM | Fleet Supervisor | Finance Manager |
|---------|---------------|----------|------------------|-----------------|
| **Salis Payment Request** *(workflow)* | Full | Read, Write, Create | Read, Write, Create | Read, Write, Submit, Cancel |
| **Approval Request** *(workflow)* | Full | Read, Write, Create, Submit | Read, Write, Create | Read |

### How segregation of duties works

- **Salis Payment Request:** the operator who *created* the request cannot also be
  the Finance Manager who *approves/pays* it. The `payment_sod_has_permission` hook
  blocks the maker from approving their own request.
- **Approval Request:** the *approver must differ from the requester*
  (`approval_sod_has_permission`). Project scoping still applies on top of this.

![screenshot: Salis Payment Request approval action]

---

## 11. Driver Portal (mobile)

A logged-in, **identity-scoped** mobile web app at **`/driver`**. Each driver only
ever sees and acts on **their own** records — the client never supplies a driver id;
the server resolves it from the signed-in user's linked **Salis Driver** record.

### What a driver can do

| Action | Endpoint behaviour |
|--------|--------------------|
| **View profile** | Read their own Salis Driver record |
| **View my vehicle** | Read the vehicle currently bound to them |
| **Today's trips** | Read today's Dispatch Trips assigned to them |
| **Check in / Check out** | Record (and submit) today's **Driver Attendance**, optionally with a photo |
| **Submit fuel request** | Raise a **Fuel Request** for their bound vehicle |
| **Raise support ticket** | File a **Support Ticket** (category, priority, subject, description) |
| **My tickets** | Read their own support tickets |

> Drivers hold only **Read** (and narrow **Create**) desk permissions — Driver
> Attendance (read/create/submit), Support Ticket (read/create), Salis Driver/Vehicle
> (read). They cannot browse other drivers' data. The portal is the intended
> surface; the desk is not.

### Notes for trainers

- The portal requires login; guests are redirected to the sign-in page.
- The portal language is **English** (drivers are multinational); the desk is Arabic.
- Appearance follows the **Salis Portal Theme** Single (AFMCO / Frappe / Dark);
  no configuration is needed for it to render with safe defaults.
- A driver user must be **linked to a Salis Driver record** (and that driver to a
  vehicle) for vehicle/fuel actions to resolve. Unlinked staff see navigation hints
  to the desk instead.

![screenshot: Driver Portal home — check-in, my vehicle, today's trips]
![screenshot: Driver Portal — submit fuel request]

---

## Appendix — automated background jobs

These run on a schedule; trainees should know the records they touch may be created
or flagged automatically:

- **Daily:** accommodation cost allocation, license-expiry checks, maintenance
  escalation, lease/temporary-stay watchlists, idle-resident aging, scheduled-task
  generation, occupancy snapshot; Salis driver-license / vehicle-compliance expiry,
  idle-vehicle, un-reverted top-up, overdue-fuel, missing-attendance watches, fuel
  accrual, rental accrual.
- **Weekly:** occupancy sync, safety-task compliance scan, vehicle-utilisation
  summary/snapshot.
- **Monthly:** rent-due alert, fuel reconciliation.

Operational anomalies surface as **Operational Alert** records and desk
notifications — review them as part of the daily routine.
