# Control Fuel from Quota to Claim

[Back to the training index](README.md)

## Outcome

Control one vehicle's monthly fuel allocation, approve and complete a fuel
request, reconcile the resulting consumption, and recognise an exception before
it becomes an unsupported payment or deduction.

## Intended role

- A **Driver** or **Fleet Supervisor** raises a Standard request.
- A **Fleet Project Manager** or **Fleet Manager**, different from the requester,
  approves or rejects it and can mark an approved request `Done`.
- A **Fleet Manager** reconciles and approves `Fuel Claim` records and resolves
  `Fuel Exception Case` records raised by someone else.
- A **Finance Manager** may review fuel records and reports but does not own the
  Fuel Request or Fuel Claim workflow actions.

## Before starting

- Use a non-production site with a training Project, Active vehicle, Active
  driver, submitted assignment, and Active `Fuel Platform`.
- Prepare separate requester and approver accounts with the same Project scope.
- Choose a current `YYYY-MM` period and a small fictional quantity and amount.
- Arrange for the site's registered daily fuel accrual to run after the request
  is completed. Do not run the exercise against a live card, chip, quota, or fill.

## End-to-end exercise

1. Create a `Fuel Quota` for the training vehicle and period with enough
   **Monthly Litres** for the exercise. A Fleet Project Manager or Fleet Manager
   submits it. Salis allows only one live quota per vehicle and period.
2. As the requester, create a **Standard** `Fuel Request` linked to that quota,
   vehicle, driver, Project, and fuel platform. Request fewer litres than remain
   on the quota. The request starts in `Pending`.
3. Record the quota's **Consumed Litres**, then change accounts. In **Fuel
   Approval Console**, approve the request. Confirm that the request is
   `Approved`, the approver differs from **Requested By**, and the quota has not
   changed yet.
4. Enter the dispense reference fields used by your operation, then use
   **Complete**. The request becomes `Done`; only now does its requested quantity
   increase the linked quota's consumption.
5. After the daily fuel accrual runs, open `Fuel Consumption Ledger` and find the
   row whose source is the completed request.
6. Create a `Fuel Claim` for the same Project, vehicle, and period. Enter the
   supplier's claimed litres and amount. Salis calculates consumed litres from
   the ledger, the unit price, and the variance.
7. As the claim maker, use **Submit to Movement**. A Fleet Manager uses
   **Reconcile** and, if the evidence supports the claim, **Approve**. The
   approver must not be the requester. Use **Dispute** instead when the totals or
   evidence do not agree.

## Decisions and exceptions

- **Standard** draws from a quota when one is linked. **Top-up** is the controlled
  route for extra litres; a temporary Top-up requires a revert due date and is
  auto-reverted by the daily watch when overdue. **Chip** records Issue, Replace,
  or Cancel; Replace and Cancel require a chip number, and Cancel also requires
  inactivity evidence and owner acknowledgement.
- A Standard request without a linked quota is not automatically refused. If the
  operation requires allocation control, confirm that the current monthly quota
  exists before approval.
- Record one fill through one consumption source. The accrual totals both `Done`
  Standard requests and `Fuel Daily Log` records; entering the same fill in both
  will count it twice. A completed request is ledgered at **Requested Litres**;
  use `Fuel Daily Log` when the authoritative source is a measured daily fill.
- Use `Fuel Exception Case` for over-consumption, GPS mismatch, duplicate claim,
  suspected fraud, quota dispute, or another documented anomaly. Evidence is
  required to resolve it, and the reporter cannot resolve their own case.
- Cancelling a ledgered Standard request restores its quota consumption and adds
  a negative ledger reversal. It does not delete the original audit row.
- `Fuel Claim`, `Fuel Quota`, and `Fuel Consumption Ledger` are operational
  records. Company and Cost Center provide reporting context; these records do
  not create a General Ledger entry or pay a supplier.

## Evidence of completion

- One submitted quota exists for the training vehicle and month.
- The request shows different **Requested By** and **Approved By** users and ends
  in `Done` through workflow actions.
- Quota consumption changed at `Done`, not at `Approved`.
- A generated ledger row identifies `Fuel Request` and the request name as its
  source.
- The claim's consumed litres equal the net ledger total for that vehicle and
  period, and its variance is explained.
- No `GL Entry`, payment document, or salary deduction was created.
- The scoped learner cannot see fuel records from another Project.

## Related links

- [Fleet and movement](fleet-movement.md)
- [Fleet compliance and financial handoffs](compliance.md)
