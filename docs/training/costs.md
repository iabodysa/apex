# 5. Costs (Facilities & Utilities)

[← Back to index](README.md)

Utility bills, accommodation cost allocation, and operational (non-financial)
depreciation.

---

## Permissions

| DocType | Accommodation Manager | Finance Manager |
|---------|----------------------|-----------------|
| Utility Account (master) | Read, Write, Create | — |
| **Utility Bill Entry** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit, Cancel |
| Operational Depreciation Policy (master) | Read, Write, Create | Read |
| Accommodation Lease | Read, Write, Create | Read |

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

### Accommodation Lease
- **Purpose:** records a rented accommodation, its term, and rent schedule.
- **Related:** Rent Payment Schedule drives monthly rent-due alerts.

### Operational Depreciation Policy
- **Purpose:** drives **non-financial** depreciation snapshots for custody/assets.
- **Note:** this is operational tracking, not a financial-ledger posting.

---

## Basic workflow

1. **Register accounts.** The Manager sets up each **Utility Account**.
2. **Enter bills.** A **Utility Bill Entry** is created per invoice and
   **Submitted**. Finance Manager can submit and **Cancel** entries.
3. **Allocate.** A daily job (`daily_accommodation_cost_allocation`) spreads costs
   to the occupancy ledger; monthly rent-due alerts run automatically.

_[screenshot: Utility Bill Entry form]_
_[screenshot: Costs workspace]_

> Cost outputs (occupancy ledger, depreciation snapshots) are **derived** records.
> Operators enter the source bills and leases; the system computes allocations.
