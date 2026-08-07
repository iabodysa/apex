# Accommodation Operations

[Back to training index](README.md)

## Audience

Accommodation Managers, Resident Supervisors, and Resident Request
Coordinators. Trainers may use a System Manager account for setup and cleanup.

## Outcome

Place a resident in an available bed, handle a housing request, and complete a
controlled checkout without bypassing occupancy or custody controls.

## Prerequisites

- A non-production training site.
- A training Employee or Temporary Worker, Project, and Cost Center.
- A training Building with at least one Room and Bed.
- Building User Permissions for any building-scoped learner.
- The [accommodation permission reference](../reference/permissions.md#accommodation-permissions).

## Operating model

Use Frappe masters for reusable structure and submitted documents for changes
that need history.

| Record | Operational purpose |
|---|---|
| `Site`, `Building`, `Room`, `Bed` | Physical hierarchy and capacity. |
| `Housing Assignment` | Submitted active stay in one bed. |
| `Room Bed Transfer` | Submitted move to another available Bed; Transfer Board limits its choices to the current Building. |
| `Housing Checkout` | Submitted end of a stay and custody-clearance gate. |
| `Resident Request` | QR or Desk intake, triage, assignment, and resolution. |

`Accommodation Ledger` and `Occupancy Snapshot` are system-written records.
Use them for traceability and reports; do not enter or correct them manually.

## Operational flow

1. Create the `Site` and `Building` masters. From a saved Building, use
   **Setup Rooms**, review the floor plan, then choose **Approve and Generate**.
   The generator creates or reconciles Rooms and Beds. Once Rooms exist, the
   Building abbreviation is locked because it forms their numbering.
2. Before check-in, confirm the Room readiness is **Ready** or **Unknown** and
   the Bed is **Available**. Use the **Front Desk** Desk page or create a
   `Housing Assignment`. Select the resident, Project, check-in date, and Cost
   Center. A temporary stay also needs an expected checkout date.

   ![Housing Assignment form showing two synthetic available beds filtered to one room.](../assets/training/accommodation/housing-assignment-bed-selection-en.png)

3. Submit the assignment. The controller locks and rechecks the Bed, marks it
   **Occupied**, and recalculates Room and Building occupancy. Housing-allowance
   suspension runs only when the Rent rule in `Salary Deduction Policy` is
   active.
4. For a move within one Building, an Accommodation Manager or System Manager
   can use **Transfer Board** or submit a `Room Bed Transfer`. Resident
   Supervisor has neither Page entry nor Create on the transfer record and must
   hand the move to an authorized role. Transfer Board blocks cross-building
   choices, but the direct DocType currently accepts a target Room in another
   Building and rewrites the assignment Building. That path does not rerun the
   full checkout and new-assignment checks. Until the application enforces one
   rule, use checkout and a new assignment for an operational cross-building
   move.
5. Triage each `Resident Request`. Setting **Assigned** requires an assignee;
   resolving or closing requires resolution notes. Maintenance, utility,
   cleaning, pest-control, and facility-item categories can create a
   `Maintenance Request`; Safety can create a `Safety Incident`; Custody can
   create a `Custody Issue`. The source keeps the target link and conversion is
   idempotent.

   ![Arabic Resident Request web form showing a synthetic pre-submission maintenance request.](../assets/training/accommodation/resident-request-intake-ar.png)

6. To end the stay, create a `Housing Checkout` from the submitted assignment.
   Resolve every outstanding custody line as **Returned**, **Lost**, or
   **Damaged**. Submission closes the assignment, releases the Bed, and marks
   the Room **Needs Cleaning**. Lost or damaged lines create a draft
   `Custody Damage Assessment` for review.
7. Verify the result in the **Housing Assignment** list view, **Checkout Pending
   Clearance**, and **Accommodation Occupancy Summary**. See the
   [automation reference](../reference/automation.md) for reconciliation,
   snapshots, expiry checks, and daily cost allocation.

Navigation and portal entry points are listed in the
[route and workspace reference](../reference/routes-workspaces.md). They do not
replace DocPerm, workflow, or Building scope.

## Non-production exercise

1. Ask the trainer for an unused training Bed and a resident with no active
   assignment.
2. Create and submit a `Housing Assignment` through Front Desk.
3. Verify the assignment is submitted, the Bed is **Occupied**, and the Room
   and Building counters changed.
4. Create a Maintenance-category `Resident Request` for the same Room.
5. Move it to **Triaged**, convert it, and verify the linked
   `Maintenance Request`.
6. With no custody outstanding, submit a `Housing Checkout`.
7. Verify the Bed is **Available**, the Room is **Needs Cleaning**, and the
   assignment carries the checkout date.

## Verification

The learner can show:

- the submitted assignment and checkout;
- the Resident Request and its linked target;
- the Bed and Room state changes;
- the Project and Cost Center retained on the assignment;
- the difference between Transfer Board policy and the direct transfer
  controller, and why operations use checkout plus a new assignment across
  Buildings.

## Cleanup and data safety

Use records clearly marked for training. Never practise on an occupied
production Bed.

For a reversible training scenario, cancel the `Housing Checkout` first with a
reason, then cancel the `Housing Assignment`. Handle the converted maintenance
draft separately. Let the trainer remove remaining draft-only training records
or reset the disposable site.

Do not edit occupancy counters or delete system-written ledger and snapshot
rows. If automation ran during the exercise, preserve its rows and use the
document cancellation or site-reset path.
