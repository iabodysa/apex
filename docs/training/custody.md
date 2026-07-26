# 2. Custody

[← Back to index](README.md)

Tracks articles and assets issued to residents/staff and their return or damage.

---

## Permissions

| DocType | Accommodation Manager | Resident Supervisor | Cleaning Supervisor |
|---------|----------------------|---------------------|---------------------|
| Custody Article (master) | Read, Write, Create, Delete | Read, Write, Create | — |
| Custody Asset Category (master) | — | — | — |
| **Custody Issue** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — |
| **Custody Return** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — |
| **Custody Damage Assessment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — |
| **Facility Asset Custody Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | — |
| **Cleaning Log** *(submittable)* | Read, Write, Create | Read, Write, Create | Read, Write, Create, Submit |

> Supervisors can **prepare** custody issues, returns, and damage assessments but
> cannot **submit** them — the Accommodation Manager submits, keeping a single
> point of accountability. **Facility Asset Custody Assignment is the exception:**
> the Resident Supervisor submits that one himself.

> **Custody Asset Category is System Manager-only.** Unlike Custody Article, it
> grants no operational role anything — treat the category list as an
> administrator setting.

> **Cleaning Log is submittable, and the Cleaning Supervisor is the one who
> submits it.** The Accommodation Manager and Resident Supervisor can prepare and
> edit a log but cannot submit it. The Resident Supervisor is building-scoped on
> Cleaning Log.

> **Internal Auditor** holds read-only oversight (Read, Report, Export) on
> Custody Issue, Custody Return, Custody Damage Assessment, Facility Asset
> Custody Assignment, and Cleaning Log.

---

## DocTypes in this area

### Custody Article / Custody Asset Category (masters)
- **Purpose:** the catalogue of issuable items and their categories.
- **Key fields:** article name, category, default value, depreciation policy link.
- **Access:** the Accommodation Manager and Resident Supervisor maintain **Custody
  Article**; **Custody Asset Category** is System Manager-only.

### Cleaning Log *(submittable)*
- **Purpose:** the per-building daily cleaning record.
- **Roles:** three roles can prepare one, but **only the Cleaning Supervisor can
  submit it** — not even the System Manager role carries Submit here.
- **Automation:** two daily jobs create today's draft logs for active buildings.

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
- **Roles:** the Resident Supervisor prepares it (Read/Write/Create); the
  Accommodation Manager submits it.
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
