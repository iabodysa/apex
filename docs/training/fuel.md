# Fuel Operations

[Back to the training index](README.md)

## Audience

Fleet operators who set quotas, raise and review fuel requests, reconcile
claims, and investigate fuel exceptions. Finance reviewers use the reports but
do not replace the fleet workflow.

## Outcome

Trace one fuel request from a monthly quota through approval, completion,
ledgering, claim reconciliation, and safe reversal.

## Prerequisites

- Use a non-production site with a training `Project`, active `Salis Vehicle`,
  active `Salis Driver`, and `Fuel Platform`.
- Prepare separate requester and reviewer accounts. Workflow self-approval is
  blocked.
- Confirm Project User Permissions before entering data. See
  **Role Permissions Manager** (`/app/permission-manager`).
- Use the shipped navigation described in
  [Modules, Workspaces, and Routes](../reference/routes-workspaces.md).

## Native records and controls

- `Fuel Quota` is a submitted monthly allocation for one vehicle and period.
- `Fuel Request` uses a Frappe Workflow for approval and completion.
- `Fuel Daily Log` records measured daily consumption.
- `Fuel Consumption Ledger` is system-written from source records. Operators
  do not create or edit it.
- `Fuel Claim` uses a Frappe Workflow and derives consumed litres from the
  ledger.
- `Fuel Exception Case` uses a Frappe Workflow for evidence and resolution.
- Attachments, timeline comments, and Version history retain supporting evidence
  and changes.

## Operational flow

### Set the quota

Create and submit one `Fuel Quota` per vehicle and month. Monthly litres must be
positive. A second live quota for the same vehicle and period is rejected.

### Raise and complete a request

`Fuel Request` supports three request types:

- Standard requires positive requested litres and can link a `Fuel Quota`.
- Top-up requires positive top-up litres. A temporary top-up also requires a
  revert due date.
- Chip records Issue, Replace, or Cancel. Replace and Cancel require a chip
  number; Cancel also requires inactivity evidence and owner acknowledgment
  before submit.

Every new request starts in `Pending`. The `Fuel Request Workflow` follows:

`Pending` → `Approved` → `Done`

Rejected requests enter `Failed`. A completed Top-up can enter `Reverted`;
submitted states can be cancelled through the available workflow action.
Approval submits the request, but a Standard request consumes its linked quota
only when it reaches `Done`. Cancelling it reverses that quota consumption.

System Manager, Fleet Manager, Fleet Project Manager, and Finance Manager can
open `Fuel Approval Console` to review the project-scoped pending queue. Fleet
Supervisor has no Page role. Approve and Reject call the same native workflow;
the console does not bypass permissions or self-approval controls.

### Reconcile claims and exceptions

`Fuel Claim` compares claimed litres with ledgered consumption for the same
vehicle and period. Its workflow follows:

`Draft` → `Submitted to Movement` → `Reconciled` → `Approved` → `Closed`

A claim can move to `Disputed` and return for reconciliation. Approval cannot be
performed by the requester. `Company` and `Cost Center` are reporting context;
the claim does not post to the General Ledger.

Use `Fuel Exception Case` for over-consumption, GPS mismatch, duplicate claim,
suspected fraud, quota dispute, or another documented anomaly. Investigate,
request evidence when needed, and resolve with evidence using a reviewer other
than the reporter.

### Review generated results

The fuel engine creates `Fuel Consumption Ledger` rows from recent
`Fuel Daily Log` records and submitted, unledgered `Done` requests. Cancellation
adds a negative reversal instead of deleting ledger history.

Use `Fuel Reconciliation`, `Fuel Spend by Vehicle`, `Fuel Claim Register`, and
`Fuel Exception Register` for review. Scheduled
accrual, overdue-request, temporary-top-up, and monthly quota checks are defined
in the [Scheduled Automation Reference](../reference/automation.md).

## Non-production exercise

1. Submit a training `Fuel Quota` with enough litres for one request.
2. Create a Standard `Fuel Request` against that quota under the training
   Project.
3. Record the quota's consumed litres before approval.
4. Approve the request with a different authorized account, then confirm the
   quota has not changed yet.
5. Complete the request and confirm the quota now includes the requested litres.
6. After the training site's normal fuel-accrual job runs, locate the generated
   ledger row by source document.
7. Create a draft `Fuel Claim` for the same vehicle and period and compare its
   consumed and variance fields with the ledger.

Do not use live quotas, cards, chips, vehicles, or employee records.

## Verification

- The quota is unique for the vehicle and month.
- The request moves through workflow actions; no field edit skips a state.
- The requester and approver are different users.
- Quota consumption changes at `Done`, not at `Approved`.
- A generated ledger row identifies the request or daily log as its source.
- Claim consumption equals the ledger total for the selected vehicle and month.
- Project filters do not expose another Project.

## Cleanup and data safety

1. Delete the draft training claim and any draft exception case.
2. Cancel the `Fuel Request` through its workflow. Confirm quota consumption is
   restored.
3. If the request was ledgered, keep the original and generated negative
   reversal rows; never delete either.
4. Cancel the training `Fuel Quota`.
5. Remove the training platform or masters only when no links remain.

Do not change read-only counters, workflow status, or ledger rows directly.
