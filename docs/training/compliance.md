# Compliance and Financial Controls

[Back to the training index](README.md)

## Audience

Fleet operators, incident reviewers, managers, and Finance reviewers.

## Outcome

Choose the correct record for compliance, suspension, incident, recovery,
cost transfer, and payment so one event is not counted or paid twice.

## Prerequisites

- Use a non-production site with a training `Project`, `Salis Vehicle`, `Salis
  Driver`, employee, company, and cost center.
- Prepare separate creator and reviewer accounts.
- Keep salary deductions and General Ledger auto-submit disabled for exercises.
- See **Role Permissions Manager** (`/app/permission-manager`) and
  [Modules, Workspaces, and Routes](../reference/routes-workspaces.md).

## Native records and controls

- `Salis Vehicle Compliance` is a child table on `Salis Vehicle`.
- `Vehicle Suspension` and `Driver Suspension` are submitted state-change
  records whose cancellation restores state when safe.
- `Vehicle Incident` is the submitted event of record.
- `Vehicle Damage Write-Off`, `Driver Clearance`, `Movement Cost Recovery`,
  `Movement Cost Transfer`, and `Salis Payment Request` use native Frappe
  Workflows where approval is required.
- `Employee Advance`, its native payment action, and `Additional Salary` handle
  employee recovery.

## Operational flow

### Maintain compliance

Add Registration, Insurance, Periodic Inspection, Operating Card, or Other rows
to the vehicle's Compliance Documents table. Each row carries an expiry date and
optional attachment. Saving `Salis Vehicle` recalculates each row's status, the
vehicle's worst compliance status, and its next expiry date.

Maintain the licence number and expiry date on `Salis Driver`. Scheduled checks
raise alerts; they do not renew documents. See
[Scheduled Automation Reference](../reference/automation.md).

### Record a stop, incident, and disposition

- Use `Vehicle Suspension` to take a vehicle out of service. Accident and
  Violation stops require evidence. Safe cancellation restores the prior state.
- Use `Driver Suspension` to stop a driver and release its vehicle. Safe
  cancellation restores prior links.
- Use `Vehicle Incident` for an Accident or Theft. An Accident records the event;
  stop the vehicle separately when required. A submitted Theft stops the vehicle
  and clears its driver.
- Use `Vehicle Damage Write-Off` for the disposition and authority decision.
  Evidence is required beyond `Open`, and higher estimated cost can require the
  higher authority tier.

Do not use a status field as a substitute for the source incident or suspension
record.

### Clear a driver

`Driver Clearance` follows:

`Open` → `In Progress` → `Cleared`

Workflow can also block, reopen, or cancel it. Clearance requires return of the
vehicle, fuel chip, and custody, plus resolution of open `Fuel Exception Case`
and `Movement Cost Recovery` records. Submitting `Cleared` releases the driver.

### Recover an employee-paid incident cost

For an incident where the company pays a driver-related amount and will recover
it from salary:

1. Record the decision on `Vehicle Incident`.
2. Set the employee, recovery amount, agreed installment, and worker signature.
3. Submit the incident. The system attempts to create exactly one linked
   `Employee Advance`.
4. Finance pays it through the native Employee Advance action.
5. After payment, the enabled `Salary Deduction Policy` Damage rule allows the
   monthly process to create a draft `Additional Salary` installment.
6. Payroll reviews and submits the installment. HRMS updates the advance's
   recovered balance and reverses it if the installment is cancelled.

Verify the incident's Recovery Advance link. Missing Accounts setup can leave
the incident submitted without an advance. Do not duplicate the incident with
`Movement Cost Recovery`.

### Route other cost controls and payments

- `Movement Cost Recovery` records another operational loss and its approval.
  It does not deduct wages or post accounting entries.
- `Movement Cost Transfer` records a cross-Project or cross-cost-center
  reallocation. `Posted (memo)` is not a General Ledger posting.
- `Salis Payment Request` follows:

  `Draft` → `Pending Finance` → `Approved by Finance` → `Paid`

  The requester cannot approve or pay it. Stop after Finance approval in this
  release. The setup wizard selects a target DocType but does not create its
  field map. Keep target auto-submit off and do not use **Create Payment** until
  Finance has reviewed and validated a complete `Payment Entry` mapping on the
  target site. Do not select `Payment Order` or a custom target.

## Non-production exercise

1. Add one future-dated and one expired compliance row to a training vehicle,
   save it, and inspect the calculated vehicle status and next expiry.
2. Submit a training `Vehicle Suspension`, confirm the vehicle becomes Stopped,
   then cancel it and confirm the prior status returns.
3. Submit an Accident `Vehicle Incident` with evidence and
   `Recover Cost from Driver` left off.
4. Create a `Vehicle Damage Write-Off` linked to the incident and move it through
   review with a different authorized user.
5. Create a small `Salis Payment Request`, submit it to Finance, and approve it
   with a different Finance user.

Stop before `Paid`, Create Payment, or any employee-recovery option.

## Verification

- Vehicle compliance shows the worst dated row and the correct next expiry.
- Suspension and cancellation preserve an auditable state change.
- Incident and write-off remain separate and linked.
- Workflow actions, not direct status edits, record each approval.
- Payment requester and Finance approver are different users.
- No exercise action creates a `GL Entry`, `Employee Advance`, or
  `Additional Salary`.

## Cleanup and data safety

1. Cancel the approved training payment request before it reaches `Paid`.
2. Cancel the write-off, then cancel the incident.
3. Confirm the suspension is already cancelled.
4. Remove only the training compliance rows and delete unlinked drafts or
   masters.

If a payment target, paid Employee Advance, or submitted salary installment
exists, stop and use the native accounting or payroll reversal. Never delete
financial history or force a workflow status.
