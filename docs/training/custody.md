# Custody Operations

[Back to training index](README.md)

## Audience

Accommodation Managers, Resident Supervisors, Procurement Supervisors, and
custody counter operators.

## Outcome

Issue and return an in-stock article with a complete audit trail, then route
damage or a durable facility asset through the correct record.

## Prerequisites

- A non-production training site.
- A training Building, Employee, and non-serialized `Custody Article`.
- Positive store balance for the article in that Building.
- Building User Permissions for any building-scoped learner.
- The [custody permission reference](../reference/permissions.md#custody-permissions).

## Operating model

Frappe submission and cancellation preserve the business documents. Apex posts
the quantity effects to its no-GL stock ledger.

| Record | Operational purpose |
|---|---|
| `Custody Asset Category`, `Custody Article` | Reusable item catalogue and return rules. |
| `Goods Receipt` | External stock received into a procurement intake store. |
| `Custody Handover` | Controlled stock handover between Buildings. |
| `Custody Issue`, `Custody Return` | Articles handed to and received from a worker. |
| `Custody Damage Assessment` | Approval and replacement-cost review for damaged or lost items. |
| `Facility Asset`, `Facility Asset Custody Assignment`, `Facility Asset Movement` | Durable equipment, supervisor custody, and location history. |

`Accommodation Stock Ledger` is system-written. It is an operational quantity
ledger, not ERPNext Stock Ledger or a General Ledger posting.

## Operational flow

1. Maintain the item catalogue. Mark serialized articles correctly; each
   serialized issue or return line must carry one serial number and a quantity
   of one.
2. Establish stock before issue. A Procurement Supervisor submits a
   `Goods Receipt` into a Building marked as a procurement intake store. Use a
   submitted `Custody Handover` when stock must move to another Building. The
   receiving side reviews, approves, and confirms the handover; confirmation
   posts the receiving ledger leg.
3. For a normal non-serialized issue, open **Custody Kiosk**, select the
   Building and worker, add the articles, capture the signature when available,
   and issue. The page submits a real `Custody Issue`; it does not bypass the
   stock or quantity checks.
4. Use the kiosk Return mode for an ordinary return. It groups lines by their
   source issue, submits one `Custody Return` per issue, blocks over-return, and
   updates the issue to **Partially Returned** or **Returned**.
5. Use the full `Custody Issue` or `Custody Return` form for serialized items.
   Use the full Return form for damaged or lost items because the kiosk does not
   capture condition. After submitting that return, choose **Create Damage
   Assessment**.
6. Send `Custody Damage Assessment` through its Frappe Workflow:
   **Draft**, **Pending Approval**, then **Approved** or **Rejected**. Approval
   records the assessed value. If the Damage rule in
   `Salary Deduction Policy` is active and the holder is an Employee, submission
   can create one draft `Additional Salary` deduction. Payroll staff must still
   review it; the assessment does not submit payroll.
7. Use `Facility Asset` for durable building equipment. A custody assignment
   changes the responsible supervisor. The movement record models location
   changes and intercompany approvals, but no role currently has Create on
   `Facility Asset Movement`; do not teach or attempt a new movement until that
   DocPerm gap is corrected.
8. Review **Custody Outstanding by Worker**, **Accommodation Stock Balance**,
   and **Custody Damage Register**. Custody expiry alerts and the weekly digest
   are described in the
   [automation reference](../reference/automation.md).

The kiosk and workspace entry points are listed in the
[route and workspace reference](../reference/routes-workspaces.md).

## Current boundaries

- A Temporary Worker can hold a `Custody Issue`, but an issue submitted without
  a linked Employee posts no store or Employee ledger legs.
- A Resident Supervisor can open Custody Kiosk, but the current DocPerm does not
  grant Submit on `Custody Issue` or `Custody Return`. An account with Submit
  permission must complete the operation.
- Custody Kiosk does not collect serial numbers or return condition. Use the
  full forms for those cases.
- `Facility Asset Movement` currently has no Create grant, including for System
  Manager. Existing records have role-specific Read, Write, Submit, and Cancel
  rights, but a normal user cannot start a new one.
- A damage assessment creates at most a draft payroll record, and only when the
  policy and salary component are configured.

## Non-production exercise

1. Ask the trainer for a pre-stocked, non-serialized training article.
2. In Custody Kiosk, select the training Building and Employee.
3. Issue one unit and capture a training signature.
4. Verify the `Custody Issue` is submitted with status **Issued**.
5. In **Custody Outstanding by Worker**, confirm the Employee holds one unit.
6. Return that unit in the kiosk.
7. Verify the linked issue is **Returned** and the store balance is restored.

## Verification

The learner can show:

- the source `Custody Issue` and `Custody Return`;
- the worker, Building, article, quantity, and signature evidence;
- the matching store and Employee legs in `Accommodation Stock Ledger`;
- the updated issue status and outstanding-custody report;
- when the full form is required instead of Custody Kiosk.

## Cleanup and data safety

Cancel the submitted `Custody Return` before cancelling its source
`Custody Issue`. A live Return blocks cancellation of the Issue, and a submitted
damage assessment blocks cancellation of its Return.

Cancellation posts reversal rows. Never delete or edit
`Accommodation Stock Ledger` to restore a balance. Do not test with serialized
production equipment, live worker custody, or a production procurement store.
