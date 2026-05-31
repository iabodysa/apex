# 2. Custody

[← Back to index](README.md)

Tracks articles and assets issued to residents/staff and their return or damage.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor |
|---------|----------------------|---------------------|
| Custody Article / Asset Category (masters) | Read, Write, Create, Delete | Read, Write, Create |
| **Custody Issue** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create |
| **Custody Return** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create |
| **Custody Damage Assessment** *(submittable)* | Read, Write, Create, Submit, Cancel | — |
| Facility Asset Custody Assignment | Read, Write, Create | Read |

> Supervisors can **prepare** custody issues and returns but cannot **submit**
> them — the Accommodation Manager submits, keeping a single point of
> accountability.

---

## DocTypes in this area

### Custody Article / Custody Asset Category (masters)
- **Purpose:** the catalogue of issuable items and their categories.
- **Key fields:** article name, category, default value, depreciation policy link.

### Custody Issue *(submittable)*
- **Purpose:** records items handed to a holder.
- **Key fields:** holder (employee), item grid, issue date.
- **On submit:** the items are placed on that person's custody.

### Custody Return *(submittable)*
- **Purpose:** records items handed back.
- **Key fields:** linked issue, returned item grid, condition.
- **On submit:** outstanding custody is reduced.

### Custody Damage Assessment *(submittable)*
- **Purpose:** records damaged/lost items returned.
- **Roles:** Manager only.
- **Feeds:** non-financial (operational) depreciation snapshots.

### Facility Asset & related
- **Facility Asset** / **Facility Asset Custody Assignment** / **Facility Asset
  Movement** track durable facility equipment and its location/holder over time.

---

## Basic workflow

1. **Define articles** in the Custody Article master (with category).
2. **Issue.** Create a **Custody Issue**, list the items and the holder, then the
   Manager **Submits** it — the items are now on that person's custody.
3. **Return.** On hand-back, create a **Custody Return** referencing the issue and
   **Submit** it; outstanding custody is reduced.
4. **Damage.** If items come back damaged, the Manager raises a **Custody Damage
   Assessment** and submits it to record the loss.

_[screenshot: Custody Issue with item grid]_
_[screenshot: Custody Kiosk desk page]_

> A **Custody Kiosk** desk page provides a fast issue/return surface for the
> front desk. See [Settings & Desk Pages](settings.md#desk-pages).
