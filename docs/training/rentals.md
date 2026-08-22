# Rental Fleet

[Back to training index](README.md)

## Outcome

Control a rented vehicle from receipt to return, reconcile the supplier's monthly claim
against daily accruals, and hand an approved settlement to Finance.

## Intended role

A **Fleet Supervisor** or **Fleet Project Manager** may prepare rental movements; a
**Fleet Manager** submits them. A Fleet Project Manager prepares the monthly
`Rental Settlement`, a Fleet Manager reconciles and approves it, and a
**Finance Manager** marks it paid only after payment evidence exists.

## Before starting

- Use a disposable training site or an isolated Company and closed period.
- Prepare a `Rental Office` linked to a fictional native ERPNext `Supplier`.
- Prepare a `Salis Vehicle` whose ownership is **Rented**.
- Use trainer-prepared `Rental Accrual Ledger` rows and separate requester, Fleet
  Manager, and Finance accounts.

## Exercise: close and reconcile one rental period

1. Prepare a `Rental Vehicle Movement` of type **Receipt** with the vehicle, office,
   date, and positive daily rate. Have a Fleet Manager submit it.
2. Confirm that a second Receipt is rejected while the first rental window is open.
3. Prepare and submit a **Return** dated after the Receipt. Record odometer, fuel level,
   condition notes, and evidence where applicable.
4. Create a `Rental Settlement` for the trainer-prepared office and month. Compare the
   claimed total, vehicle-line accrued total, ledger accrued total, and both variance
   fields.
5. As Fleet Manager, choose **Reconcile**. Resolve a discrepancy through **Dispute** and
   **Re-reconcile** if needed.
6. Have a Fleet Manager who is not the requester choose **Approve**.
7. Confirm that eligible accrual rows now carry the settlement link and are marked
   settled. Stop before **Mark Paid** in the training exercise.

## Decisions and exceptions

- A Return requires an open Receipt and cannot precede it. A Receipt requires a daily
  rate and only accepts a vehicle whose ownership is **Rented**.
- The daily job creates at most one original `Rental Accrual Ledger` row per vehicle and
  date while its latest submitted movement is a Receipt. Operators must not create,
  edit, or delete these rows.
- Settlement approval does not post accounting. **Raise Payment Request** creates one
  linked `Salis Payment Request` for the payable amount; Finance approval and the
  configured **Create Payment** route are separate controls.
- **Mark Paid** is restricted to Finance and cannot be performed by the requester. The
  label itself is not General Ledger evidence; Finance must verify the linked routed
  payment.
- Cancelling an approved settlement releases its accrual rows for a replacement. Cancel
  the Return before cancelling its Receipt.

## Evidence of completion

Show the ordered Receipt and Return, the settlement totals and variances, approval by a
non-requester, and accrual rows linked to the approved settlement. Confirm that the
exercise created no General Ledger entry.

## Related links

- [Fleet and movement](fleet-movement.md)
- [Fleet compliance and financial handoffs](compliance.md)
