# 8. Rentals (Salis)

[← Back to index](README.md)

Rented vehicles: registering offices, accruing cost, and settling.

---

## Permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| Rental Office (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read |
| Rental Vehicle Movement | Full | Read, Write, Create | Read, Write, Create | Read |
| **Rental Settlement** *(workflow)* | Full | Read, Write, Create | — | Read, Write |

---

## DocTypes in this area

### Rental Office (master)
- **Purpose:** an external office that supplies rented vehicles.
- **Key fields:** office name, contact, contract terms.

### Rental Vehicle Movement
- **Purpose:** records a rented vehicle entering/leaving service.
- **Feeds:** the rental accrual ledger.

### Rental Settlement *(workflow)*
- **Purpose:** the periodic reconciliation/payment against a rental office.
- **Roles:** Finance Manager reviews and writes settlement figures; Fleet Manager
  closes.
- **Related:** Rental Settlement Item (lines), Rental Accrual Ledger (derived).

---

## Basic workflow

1. **Register offices** providing rented vehicles.
2. **Accrue.** A daily rental-accrual job posts rental cost to the accrual ledger.
3. **Settle.** A **Rental Settlement** runs the *Rental Settlement Workflow*;
   Finance Manager reviews and writes the settlement figures; Fleet Manager closes
   it.

_[screenshot: Rental Settlement form]_

> The accrual ledger is **derived** automatically — operators register movements
> and offices; the daily job builds the accrual.
