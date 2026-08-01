# 5. Costs (Facilities & Utilities)

[← Back to index](README.md)

Utility bills, accommodation cost allocation, and operational (non-financial)
depreciation.

---

## Permissions

The exact grants for these records are in the [permissions reference](../reference/permissions.md#habitat), generated from the shipped DocPerm JSON.

> **Finance Manager is a full maker/checker on the Lease and Utility
> Bill Entry** — Read, Write, Create, Submit, and Cancel (not read-only). The
> **Internal Auditor** holds read-only oversight across the Costs records —
> Lease, Accommodation Ledger, Utility Bill Entry, Occupancy Snapshot, and
> Accommodation Stock Ledger.

> **Operational Depreciation Policy is System Manager-only.** No operational role
> holds any right on it — not the Accommodation Manager and not the Finance
> Manager. Treat it as an install-time setting, changed only by an administrator.

---

## DocTypes in this area

### Utility Account (master)
- **Purpose:** one record per utility provider/meter (electricity, water, etc.).
- **Key fields:** account name, utility type, building/site link.

### Utility Bill Entry *(submittable)*
- **Purpose:** one invoice posting.
- **Roles:** Manager enters; Finance Manager can also submit and **cancel** as the
  cost-control owner.
- **Key fields:** account, period, amount, building.

### Lease *(submittable)*
- **Purpose:** records a rented accommodation, its term, and rent schedule.
- **Related:** **Rent Payment Schedule** is the child table behind the lease's
  *Rent Payment Schedule* grid — one row per scheduled payment, carrying a due
  date, an amount, and a status of Unpaid, Paid, or Overdue.
- **No rent alerting ships.** Nothing reads or writes those rows automatically:
  there is no rent-due job, notification, or alert. Someone must review the grid
  and set each row's status by hand. The only lease automation is the **daily**
  lease-expiry job, which flips a lease past its end date to *Expired*.

### Operational Depreciation Policy
- **Purpose:** drives **non-financial** depreciation snapshots for custody/assets.
- **Note:** this is operational tracking, not a financial-ledger posting.
- **Access:** System Manager only — see the permissions note above.

---

## Basic workflow

1. **Register accounts.** The Manager sets up each **Utility Account**.
2. **Enter bills.** A **Utility Bill Entry** is created per invoice and
   **Submitted**. Finance Manager can submit and **Cancel** entries.
3. **Allocate.** A daily job (`daily_accommodation_cost_allocation`) fans one
   idempotent job out per building and spreads the day's cost into the
   **Accommodation Ledger**.
4. **Track rent by hand.** Keep each **Rent Payment Schedule** row on the lease
   up to date yourself — no job flags a payment as due or overdue.

_[screenshot: Utility Bill Entry form]_
_[screenshot: Costs workspace]_

> Cost outputs (Accommodation Ledger, depreciation snapshots) are **derived**
> records. Operators enter the source bills and leases; the system computes
> allocations.
