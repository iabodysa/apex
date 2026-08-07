# Maintenance Operations

[Back to training index](README.md)

## Audience

Requesters, Resident Supervisors, Accommodation Managers, Maintenance
Technicians, and System Managers who issue work orders.

## Outcome

Turn a reported fault into a controlled work order, capture completion evidence,
and understand which records are operational memos rather than purchasing or
accounting documents.

## Prerequisites

- A non-production training site.
- A training Building and Room.
- Separate training accounts for request handling, work-order issue, and
  technician execution where practical.
- The **Role Permissions Manager** (`/app/permission-manager`).

## Operating model

Use the submitted Frappe documents as the audit trail. Desk buttons call the
same controllers as the forms; they do not write status or cost directly.

| Record | Operational purpose |
|---|---|
| `Maintenance Request` | Report, priority, location, assignment, and resolution. |
| `Maintenance Work Order` | Planned work, technician action, evidence, and operational cost. |
| `Maintenance Inspection Report` | Optional System Manager inspection linked to a facility asset or work order. |
| `Maintenance Material Template` | Reusable draft procurement lines; it creates no purchase or stock transaction. |
| `Maintenance Cost Ledger` | System-written cost row for each positive-cost procurement line. |
| `Subcontractor Service Contract`, `Subcontractor Service Order` | External coverage and visit execution. |

## Operational flow

1. Create a `Maintenance Request` with Building, Room, issue type, priority, and
   description. Any signed-in user can create their own request; operational
   roles triage and submit it. Setting **Assigned** requires an assignee, and
   resolving or closing requires resolution notes.
2. While the request is Draft, **Load Material Template** can append matching
   procurement lines. Review the result: the action does not create a
   `Material Request`, `Purchase Order`, stock entry, or accounting record.
3. Submit the request with status **Open**. From it, choose **Create Work
   Order**. Only an account with Work Order Create and Submit rights can finish
   that step under the current permission model.
4. On the draft `Maintenance Work Order`, enter the planned dates, work
   description, assignee, and any procurement lines. Enter actual start and end
   dates before submission if this record will be completed through the current
   Desk controls.
5. Submit the Work Order. Its status becomes **Planned** and the source request
   becomes **In Progress**. A Maintenance Technician with write access can use
   **Start Work**, attach the required completion photo, then use **Mark as
   Completed**.
6. Completion requires actual start and end dates plus the photo. It closes the
   source request and, when procurement cost is positive, writes one aggregate
   `Accommodation Ledger` memo plus one `Maintenance Cost Ledger` row per
   positive-cost procurement line. These are operational records; completion
   does not create a General Ledger Entry, Payment Entry, Purchase Invoice, or
   salary record.
7. For external work, use an approved `Subcontractor Service Contract`, then
   submit a `Subcontractor Service Order`. Use **Start Work**, then the
   controlled **Mark as Completed** or **Mark Missed** action.
8. Review **Maintenance Aging**, whose status filter also lists the open
   requests. The daily
   overdue thresholds and alert effects are listed in the
   [automation reference](../reference/automation.md).

`Maintenance Inspection Report` is currently restricted to System Manager. It
requires at least one finding and updates a linked `Facility Asset` inspection
date when submitted.

## Current boundary

`Maintenance Work Order` completion requires actual start and end dates, but
those fields are not editable after submission in the shipped form. Record them
on the draft before submission until the execution flow is corrected.

## Non-production exercise

1. Create a low-priority `Maintenance Request` for the training Room and submit
   it as **Open**.
2. With the authorized training account, use **Create Work Order**.
3. Enter planned and actual dates, work description, and no procurement cost.
4. Submit the Work Order.
5. With the technician account, choose **Start Work**.
6. Attach a non-sensitive training image and choose **Mark as Completed**.
7. Verify the Work Order is **Completed** and the source request is **Closed**.

## Verification

The learner can show:

- the submitted request and its linked Work Order;
- the transition from **Planned** to **In Progress** to **Completed**;
- actual dates, completion photo, and timeline comments;
- that a zero-cost exercise created no operational cost row;
- why a material template is not a purchasing transaction.

## Cleanup and data safety

An authorized user may cancel the training Work Order with a reason. Cancellation
reopens a source request that was **In Progress** or **Closed** and reverses any
operational cost the Work Order posted. Cancel the request afterwards if the
training scenario is no longer needed.

Never delete an original `Accommodation Ledger` or `Maintenance Cost Ledger`
row. Preserve its reversal. Do not use a live facility asset, production room,
supplier contract, or real completion photo in training.
