# Rental Fleet

[Back to the training index](README.md)

## Audience

Fleet operators who receive and return rented vehicles, reconcile rental
charges, and hand approved settlements to Finance.

## Outcome

Maintain an auditable rental window from vehicle receipt through daily
operational accrual, monthly settlement, Finance review, and cancellation.

## Prerequisites

- Use a disposable training site or an isolated training company and period.
- Prepare a training `Supplier`, `Rental Office`, and `Salis Vehicle` whose
  ownership is `Rented`.
- Prepare separate settlement requester, fleet reviewer, and Finance reviewer
  accounts.
- Review **Role Permissions Manager** (`/app/permission-manager`)
  and the shipped workspace in
  [Modules, Workspaces, and Routes](../reference/routes-workspaces.md).

## Native records and controls

- `Supplier` is the native ERPNext counterparty linked from `Rental Office`.
- `Rental Office` stores the fleet-facing office and contact details.
- `Rental Vehicle Movement` is the submitted Receipt or Return record.
- `Rental Accrual Ledger` is a system-written operational memo. It is not a
  General Ledger.
- `Rental Settlement` uses a Frappe Workflow to reconcile, approve, and mark the
  period paid.
- `Salis Payment Request` is the controlled handoff to Finance. Its **Create
  Payment** action remains unavailable until Finance validates a complete
  `Payment Entry` field map on the target site.

## Operational flow

### Open and close the rental window

1. Link `Rental Office` to the native `Supplier`.
2. Set the fleet vehicle's ownership to `Rented` and link its rental office.
3. Submit a `Rental Vehicle Movement` of type `Receipt` with the vehicle, office,
   date, and positive daily rate.
4. When the vehicle leaves service, submit a `Return` with its date, odometer,
   fuel level, condition notes, and evidence as applicable.

The controller rejects a duplicate open Receipt, a Return without an open
Receipt, and a Return dated before its Receipt.

### Accrue and settle

While the latest submitted movement is a Receipt, the rental engine creates one
`Rental Accrual Ledger` row per vehicle and day. Re-running the job does not
create a second row for the same vehicle and date. Each row is an operational
memo and posts no accounting entry.

Create one `Rental Settlement` for the office and month. Vehicle lines calculate
the accrued total; the controller also reads the generated ledger total and
shows both the claimed variance and ledger variance.

The `Rental Settlement Workflow` follows:

`Draft` → `Reconciled` → `Approved` → `Paid`

A reconciled settlement can be disputed and re-reconciled. The requester cannot
approve or mark their own settlement paid. Approval submits the settlement and
stamps its eligible accrual rows as settled. Cancelling an approved settlement
releases those rows for a replacement settlement.

An approved settlement can supply one linked `Salis Payment Request` as the
controlled Finance handoff. Neither settlement approval nor the `Paid` label
posts to the General Ledger. Stop at the approved settlement and linked
request. Keep the payment target on `Payment Entry`, keep target auto-submit
off, and do not use **Create Payment** until its complete field map has passed
Finance review.

Use `Rental Cost by Office` and `Rental Settlement Register` to review monthly
cost and settlement state. The registered daily and monthly jobs are described
in the [Scheduled Automation Reference](../reference/automation.md).

## Non-production exercise

Use a trainer-prepared period that already contains generated training accrual
rows.

1. Submit a Receipt for a rented training vehicle.
2. Attempt a second Receipt and confirm the lifecycle guard rejects it.
3. Submit a Return dated after the Receipt.
4. Create a `Rental Settlement` for the prepared office and period.
5. Compare vehicle-line accrued total, ledger accrued total, claimed total, and
   both variance fields.
6. Reconcile and approve with different authorized users, then stop.
7. Confirm the period's generated accrual rows now link to the settlement.

Do not move to `Paid` or create a payment document during training.

## Verification

- The submitted Receipt and Return form a valid, ordered rental window.
- The ledger contains at most one original row per vehicle and date.
- Settlement totals match the intended vehicle lines and generated ledger.
- The requester does not approve their own settlement.
- Approved accrual rows show the settlement link and settled flag.
- No `GL Entry` is created by a movement, accrual, or settlement action.

## Cleanup and data safety

1. Cancel the approved training settlement before it reaches `Paid`; confirm its
   accrual rows are released.
2. Cancel the Return, then cancel the Receipt.
3. Delete only unused training drafts and unlinked training masters.

Do not hand-create, edit, or delete `Rental Accrual Ledger` rows. A scheduler may
create new rows for any open Receipt, so use a disposable site or close the
training rental before leaving the exercise.
