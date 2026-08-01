# 1. Accommodation

[← Back to index](README.md)

Master data (sites, buildings, rooms, beds) underpins the day-to-day assignment,
checkout, and resident-request records.

---

## Permissions

The exact grants for these records are in the [permissions reference](../reference/permissions.md#habitat), generated from the shipped DocPerm JSON.

> **Site is Manager-only.** Unlike Building, Room, and Bed, the **Site** master
> grants the Resident Supervisor nothing — supervisors read the building
> hierarchy from Building downwards.

> **Resident Request Coordinator** is the dedicated triage role for resident
> requests: it holds Read/Write/Create on **Resident Request**.

> **Building scoping:** a Resident Supervisor sees only his assigned buildings' records (Housing Assignment, Custody Issue, Cleaning Log). Set scope via *User Permission* on **Building**. Oversight roles are unscoped.

> **Triage-field split:** the three housing roles — Accommodation Manager,
> Resident Supervisor, and Resident Request Coordinator — hold Read/Write on the
> `permlevel 1` triage fields of Resident Request, separating resident-entered
> data from internal triage handling.

> **Internal Auditor** holds read-only oversight (Read, Report, Export) on
> **Facility Asset**. It holds nothing on the Site/Building/Room/Bed masters or
> on the assignment and checkout records.

---

## DocTypes in this area

### Site / Building / Room / Bed (masters)
- **Purpose:** the physical housing hierarchy — Site → Building → Room → Bed.
- **Roles:** Accommodation Manager maintains; supervisors read Building, Room,
  and Bed to pick beds. Site is Manager-only.
- **Key fields:** name/code, capacity, status (active/inactive), parent link.

### Housing Assignment *(submittable)*
- **Purpose:** places a resident in a specific bed.
- **Roles:** supervisors prepare and submit; only the Manager can cancel or amend.
- **Key fields:** employee/resident, bed, start date, project.
- **On submit:** marks the bed **Occupied**, re-derives the room's and building's
  occupancy counts, and suspends the housing allowance when the *Rent* rule of the
  Salary Deduction Policy is active. It writes **no** ledger row — accommodation
  cost reaches the **Accommodation Ledger** later, through the daily allocation
  job.

### Housing Checkout *(submittable)*
- **Purpose:** records a resident leaving and frees the bed.
- **Roles:** supervisors prepare and submit; Manager cancels if raised in error.
- **Key fields:** assignment reference, checkout date, condition notes.

### Resident Request
- **Purpose:** resident self-service intake (maintenance, complaint, move).
- **Roles:** filed by residents via QR web form; triaged by Manager/supervisors.
- **Key fields:** request type, location (QR), description, status.

---

## Basic workflow

1. **Set up masters once.** The Accommodation Manager creates the Site → Building
   → Room → Bed hierarchy. Supervisors have read access so they can pick beds.
2. **Assign a resident.** A supervisor creates a **Housing Assignment**,
   selects the employee and an available bed, and **Submits** it. Submission marks
   the bed occupied and re-derives the room and building occupancy counts.
3. **Check out.** When a resident leaves, create a **Housing Checkout** and
   **Submit** it to free the bed. Only the Accommodation Manager can **Cancel** a
   submitted assignment or checkout if it was raised in error.
4. **Resident self-service.** Residents scan a **QR Location** and
   file a **Resident Request**. The Manager and supervisors triage
   these from the desk.

_[screenshot: Housing Assignment form with bed selection]_
_[screenshot: Resident Request intake via QR web form]_

> Related background jobs (all daily): occupancy snapshot, lease expiry,
> idle-resident aging, temporary-worker linking, and the accommodation cost
> allocation that builds the Accommodation Ledger. A weekly occupancy sync also
> runs. See [Background Jobs](settings.md#background-jobs).
