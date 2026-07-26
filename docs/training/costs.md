# Costs and Leasing

[Back to training index](README.md)

## Audience

Accommodation Managers who prepare facility costs, Finance Managers who approve
leases and payments, and Internal Auditors who review source-to-ledger history.

## Outcome

Approve a utility bill or lease through its Frappe Workflow, distinguish an
operational memo from an accounting posting, and verify the source link.

## Prerequisites

- A non-production training site.
- A training Company, Building, Supplier, and Cost Center.
- Two Accommodation Manager training users for the Utility Bill approval
  exercise because self-approval is blocked.
- A Finance Manager training user for Lease approval.
- The [cost and leasing permission reference](../reference/permissions.md#cost-and-leasing-permissions).

## Operating model

Use Frappe Workflow for approval and ERPNext payment documents for payment.
Apex keeps facility allocation in a separate no-GL operational ledger.

| Record | Operational purpose |
|---|---|
| `Utility Account` | Provider account, meter, Building, average, and sharing rule. |
| `Utility Bill Entry` | Billing period, readings, Building share, and approval. |
| `Lease` | Landlord, term, billing cycle, rent, and payment schedule. |
| `Accommodation Ledger` | System-written direct costs and resident allocations. |
| `Operational Depreciation Policy` | Non-financial useful-life calculation rules. |

## Utility bill flow

1. Create one `Utility Account` per provider account or meter and Building.
   Record the average monthly bill and variance threshold when they are known.
2. Create a `Utility Bill Entry`. Billing periods for the same Company,
   Building, and account cannot overlap.
3. For a shared meter, enter the full invoice in **Total Invoice Amount** and
   the Building percentage in **Cost Bearing**. The system computes
   **Bill Amount**, consumed units, sharing note, and variance from average.
4. Use the Frappe Workflow: **Submit for Approval**, then have a different
   Accommodation Manager choose **Approve** or **Reject**. Approval submits the
   document.
5. Submission writes one direct `Accommodation Ledger` row for the Building's
   share. It does not create a Payment Entry, Purchase Invoice, or General
   Ledger Entry.
6. Cancellation requires a reason and writes a negative reversal memo. Preserve
   both rows.

## Lease and payment flow

1. Create a `Lease` with Building, landlord, start and end dates, rent, billing
   cycle, and first payment date. Overlapping leases for one Building are
   blocked.
2. Saving the draft builds the `Rent Payment Schedule`. If its driving values
   change while still Draft, use **Regenerate Payment Schedule** and review every
   replacement row.
3. Use **Submit for Approval**. A Finance Manager approves or rejects; approval
   submits the Lease.
4. Do not use **Generate Payment** in production. It currently opens an unsaved
   Payment Entry with no accounting reference allocation. Its `reference_no`
   value is descriptive and does not allocate the Lease or a payable document.
5. Finance uses the native payable path: create the Purchase Order first when
   site policy requires it, approve the landlord's Purchase Invoice for the rent
   period, then create a Payment Entry whose References table allocates the
   amount to that Purchase Invoice.
6. Maintain the schedule row status only from verified native invoice and
   payment evidence. Lease approval and the incomplete button do not prove bank
   or General Ledger posting.
7. Lease-expiry Notifications ship enabled. The rent-due Notification ships
   disabled because no automatic process confirms that a schedule row was paid.
   See the [automation reference](../reference/automation.md).

## Allocation and system-written boundaries

The daily accommodation allocator reads active submitted
`Housing Assignment` records and positive annual Building costs. It writes an
idempotent resident-and-cost-type `Accommodation Ledger` row using Building
capacity. A Temporary Worker without an Employee link is skipped until the
linking process can backdate the missed rows.

A submitted Utility Bill writes its own direct billing-period memo. It does not
update the Building's annual utility estimate.

`Accommodation Ledger` is read-only to human roles and posts no GL entry.
`Operational Depreciation Snapshot` is also non-financial and currently has no
human Create permission; do not treat it as an operator input form.

## Non-production exercise

1. Create a training `Utility Account` with an average monthly bill.
2. Create a bill for a unique training period with a total invoice of
   `SAR 1,000` and a Building share of `60%`.
3. Verify the computed Bill Amount is `SAR 600` and review the variance.
4. Submit it for approval.
5. Sign in as the second Accommodation Manager and approve it.
6. Open `Accommodation Ledger` and find the one original row whose Source
   DocType and Source Document point to the bill.
7. Confirm that no payment or General Ledger document was created.

## Verification

The learner can show:

- the approved source bill and its non-overlapping period;
- the full invoice, percentage, computed share, and variance;
- the source-linked operational ledger row;
- the second-user approval history;
- why approval is not evidence of payment or GL posting.

## Cleanup and data safety

An authorized user may cancel the training bill with a clear reason. Verify a
reversal memo was added; never delete the original ledger row.

Do not generate a payment against a real Supplier for practice. If the Lease
exercise is used, do not use **Generate Payment**. Review only
trainer-prepared native payable records or the documented flow. This does not
validate the separate `Salis Payment Request` field map or authorize its
**Create Payment** action. Never change a production payment-schedule row
without verified payment evidence.
