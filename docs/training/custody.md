# Custody Operations

[Back to training index](README.md)

## Outcome

Issue and return a custody article with a traceable holder, Building balance, and source
document, then send damaged items or durable assets through the correct follow-up.

## Intended role

An **Accommodation Manager** completes normal issues and returns. A
**Resident Supervisor** may prepare them and open **Custody Kiosk**, but cannot submit
`Custody Issue` or `Custody Return`. A **Procurement Supervisor** receives external
stock and participates in Building-to-Building handover.

## Before starting

- Use a disposable training site, a fictional Employee, and a Building in scope.
- Prepare a non-serialized `Custody Article` with positive store balance in that
  Building.
- Use an Accommodation Manager account for the kiosk exercise.
- Use a sanitized training signature; never capture a real worker signature.

## Exercise: issue and return one article

1. Open **Custody Kiosk**, choose **Employee**, select the training worker and Building,
   and add one unit of the article.
2. Capture the training signature and issue the cart.
3. Open the resulting `Custody Issue`. Confirm it is submitted with status **Issued**.
4. In **Accommodation Stock Balance**, verify that the Building store decreased by one
   and the Employee holding increased by one.
5. Change the kiosk to **Return**, select the same worker and article, and complete the
   return.
6. Confirm the new `Custody Return` is submitted, the source issue is **Returned**, and
   the Building store balance is restored.

## Decisions and exceptions

- Use the full `Custody Issue` and `Custody Return` forms for serialized articles. Each
  serialized line requires one serial number and quantity one.
- Use the full Return form for **Damaged** or **Lost** condition. Then choose
  **Create Damage Assessment** and send the `Custody Damage Assessment` through
  **Submit for Approval** and **Approve** or **Reject**. A different Accommodation
  Manager must approve it.
- A damage assessment may create a draft `Additional Salary` deduction only for a
  linked Employee when the Damage policy is active. Payroll must still review it.
- A Temporary Worker may be selected in the kiosk, but an issue with no linked Employee
  posts no store or holder ledger movement. Do not treat that case as stock evidence.
- A Procurement Supervisor records external stock in `Goods Receipt` at a Building
  marked as a procurement store. A `Custody Handover` then follows **Pending Receipt**,
  **Under Review**, **Approved**, and **Confirmed**; the shipper and receiver must be
  different people, and confirmation uses the one-time code when enabled.
- Use `Facility Asset Custody Assignment` for supervisor responsibility and
  `Facility Asset Movement` for location changes. Intercompany movements require
  release and receiving confirmation; permanent intercompany movement also requires
  accounting acknowledgement before submission.
- `Accommodation Stock Ledger` is an operational quantity record, not accounting stock
  or a General Ledger. Never edit or delete it.

Cancel a `Custody Return` before its source issue. A submitted damage assessment must be
handled before its return can be cancelled.

## Evidence of completion

Show the submitted issue and return, worker signature evidence, article and quantities,
the source-to-return link, the updated issue status, and the matching Building and
Employee balance changes.

## Related links

- [Accommodation operations](accommodation.md)
- [Costs and leasing](costs.md)
- [Scheduled automation](../reference/automation.md)
