# 1. Accommodation

[← Back to index](README.md)

Master data (sites, buildings, rooms, beds) underpins the day-to-day assignment,
checkout, and resident-request records.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor | Finance Manager |
|---------|----------------------|---------------------|-----------------|
| Accommodation Site / Building | Read, Write, Create | Read | — |
| Accommodation Room / Bed | Read, Write, Create | Read | — |
| Facility Asset | Read, Write, Create | Read | — |
| **Accommodation Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit | — |
| **Accommodation Checkout** *(submittable)* | Read, Write, Create, Submit, Cancel | Read, Write, Create, Submit | — |
| Accommodation Resident Request | Read, Write, Create | Read, Write, Create | — |

---

## DocTypes in this area

### Accommodation Site / Building / Room / Bed (masters)
- **Purpose:** the physical housing hierarchy — Site → Building → Room → Bed.
- **Roles:** Accommodation Manager maintains; supervisors read to pick beds.
- **Key fields:** name/code, capacity, status (active/inactive), parent link.

### Accommodation Assignment *(submittable)*
- **Purpose:** places a resident in a specific bed.
- **Roles:** supervisors prepare and submit; only the Manager can cancel.
- **Key fields:** employee/resident, bed, start date, project.
- **On submit:** marks the bed occupied and posts to the occupancy ledger.

### Accommodation Checkout *(submittable)*
- **Purpose:** records a resident leaving and frees the bed.
- **Roles:** supervisors prepare and submit; Manager cancels if raised in error.
- **Key fields:** assignment reference, checkout date, condition notes.

### Accommodation Resident Request
- **Purpose:** resident self-service intake (maintenance, complaint, move).
- **Roles:** filed by residents via QR web form; triaged by Manager/supervisors.
- **Key fields:** request type, location (QR), description, status.

---

## Basic workflow

1. **Set up masters once.** The Accommodation Manager creates the Site → Building
   → Room → Bed hierarchy. Supervisors have read access so they can pick beds.
2. **Assign a resident.** A supervisor creates an **Accommodation Assignment**,
   selects the employee and an available bed, and **Submits** it. Submission marks
   the bed occupied and posts to the occupancy ledger.
3. **Check out.** When a resident leaves, create an **Accommodation Checkout** and
   **Submit** it to free the bed. Only the Accommodation Manager can **Cancel** a
   submitted assignment or checkout if it was raised in error.
4. **Resident self-service.** Residents scan an **Accommodation QR Location** and
   file an **Accommodation Resident Request**. The Manager and supervisors triage
   these from the desk.

_[screenshot: Accommodation Assignment form with bed selection]_
_[screenshot: Resident Request intake via QR web form]_

> Related background jobs: occupancy snapshot, lease/temporary-stay watchlists,
> idle-resident aging. See [Background Jobs](settings.md#background-jobs).
