# Costs and Leasing

[Back to training index](README.md)

## Outcome

Approve a Building's share of a utility bill, prove the source-to-cost trail, and hand
lease payments to Finance through an allocated payable rather than an unreferenced
payment.

## Intended role

An **Accommodation Manager** prepares utility bills and leases. A different
Accommodation Manager approves a `Utility Bill Entry`; a **Finance Manager** approves
or rejects a `Lease` and reviews accounting documents. An **Internal Auditor** reads
the source and operational ledger history.

## Before starting

- Use a disposable training site with a fictional Company, Building, Cost Center,
  Supplier, and `Utility Account`.
- Prepare two Accommodation Manager accounts for the utility approval.
- Give the bill a billing period that does not overlap another bill for the same
  Company, Building, and Utility Account.
- Never use a live landlord, supplier invoice, or bank account in training.

## Exercise: approve a shared utility bill

1. Set the training `Utility Account` average monthly bill to a known value.
2. Create a `Utility Bill Entry` for a unique period. Enter **SAR 1,000** as
   **Total Invoice Amount** and **60%** as **Cost Bearing**.
3. Save and confirm that **Bill Amount** is **SAR 600**. Review the sharing note,
   consumed units where readings were supplied, and variance from the account average.
4. Choose **Submit for Approval**.
5. Sign in as the second Accommodation Manager and choose **Approve**.
6. Find the `Accommodation Ledger` row whose source is this bill. Confirm its direct
   cost is SAR 600 and that the billing period and Building match.
7. Confirm that approval created no Purchase Invoice, Payment Entry, or General Ledger
   posting.

## Decisions and exceptions

- The current meter reading cannot be below the previous reading. Bill amounts cannot
  be negative, and overlapping periods are blocked.
- `Accommodation Ledger` is a read-only operational cost record. Cancellation requires
  a reason and adds a negative reversal; never delete the original.
- A draft `Lease` builds its `Rent Payment Schedule` from the term, billing cycle, rent,
  and first payment date. Review the rows before **Submit for Approval**. Finance uses
  **Approve** or **Reject**; an Accommodation Manager then uses **Activate**.
- Before using **Generate Payment**, Finance must have submitted the landlord's native
  ERPNext `Purchase Invoice`. The payment target must be configured as `Payment Entry`.
  Select the lease instalment and outstanding invoice; the action creates one draft
  `Payment Entry` whose References table allocates the payable, or returns the payment
  already raised for that instalment.
- `Generate Payment` never submits the Payment Entry. Finance must review and submit it.
  The lease schedule and lease status alone are not proof of payment or General Ledger
  posting.
- A submitted utility bill records its own period cost; it does not update the
  Building's annual utility estimate. Operational depreciation snapshots are
  system-created, not operator input.

## Evidence of completion

Show the approved bill, second-user approval history, full invoice and Building share,
variance, and the source-linked operational ledger row. State clearly that no accounting
payment was created by the exercise.

## Related links

- [Accommodation operations](accommodation.md)
- [Rentals](rentals.md)
