# Manage Fleet Compliance and Financial Handoffs

[Back to the training index](README.md)

## Outcome

Record a vehicle compliance issue and incident with the correct operational
records, preserve maker-checker approval, and hand a payable item to Finance
without confusing an operational memo with accounting or payroll.

## Intended role

- **Fleet Supervisors** prepare compliance, suspension, incident, write-off,
  recovery, and payment-request records within their Project scope.
- **Fleet Project Managers** prepare cross-Project cost transfers and, with Fleet
  Managers, submit suspensions. A Fleet Manager submits incidents and owns
  Operations-tier approvals and reversals.
- **Government Relations Officers** and **Internal Auditors** inspect the records
  granted to them; they do not perform fleet workflow actions.
- **Finance Managers** approve `Salis Payment Request` records only. Payroll and
  Accounts own any later HRMS or ERPNext transaction.

## Before starting

- Use a non-production site with a training Project, vehicle, driver, employee,
  Company, and Cost Center.
- Prepare separate fleet maker, fleet approver, and Finance Manager accounts.
- Keep **Enable GL Entry Posting** and salary deductions off for this exercise.
- Use fictional reports, photos, signatures, amounts, and reference numbers.
  Never rehearse with a real accident, worker debt, or payment.

## End-to-end exercise

1. On the training `Salis Vehicle`, add one future-dated and one expired row to
   **Compliance Documents**, then save. Confirm that each row is classified and
   the vehicle shows the worst compliance state and its next expiry date.
2. As the fleet maker, create an Accident `Vehicle Incident` with description and
   fictional evidence. Leave **Recover Cost from Driver** clear. A Fleet Manager
   submits the incident. The Accident records the event but does not stop the
   vehicle.
3. If the training scenario says the vehicle is unsafe, create a separate
   `Vehicle Suspension` with reason **Accident** and evidence. A Fleet Project
   Manager or Fleet Manager submits it and confirms the vehicle is `Stopped`.
4. Create a `Vehicle Damage Write-Off` linked to the incident. Enter the proposed
   disposition, estimated cost, and evidence, then use **Submit for Review**. A
   different authorized user applies the Regional or Operations action shown by
   the workflow. Confirm that the approved case is linked back to the incident.
5. Create a small `Salis Payment Request` for the approved operational expense,
   linking the incident or write-off as its reference. Use **Submit to Finance**.
6. Change to the Finance Manager account, review the source, Company, Cost Center,
   Project, supplier, and amount, then use **Approve (Finance)**. Stop at
   `Approved by Finance`; do not use **Create Payment** or **Mark Paid** in this
   exercise.

## Decisions and exceptions

- A compliance row proves a dated document. `Vehicle Suspension` changes service
  state. `Vehicle Incident` records the event. `Vehicle Damage Write-Off` records
  the disposition and authority. Do not replace one with another.
- A submitted Theft incident stops the vehicle and clears its driver. An Accident
  does neither; use a suspension when an Accident also requires a stop.
- `Driver Clearance` is for fleet exit clearance, not HR end-of-service or visa
  clearance. **Clear** is available only after vehicle, fuel chip, and custody are
  returned and open fuel exceptions and movement recoveries are resolved. A
  cleared driver becomes `Released` and their driver portal credential is revoked.
- `Movement Cost Recovery` documents an operational loss and its authority. It
  does not deduct wages or post accounting. `Movement Cost Transfer` is also a
  no-GL memo; `Posted (memo)` is not a journal entry.
- For a driver-related incident that will be recovered from pay, use the
  `Vehicle Incident` recovery fields once, with the employee, amount, installment,
  and worker signature. Submission raises one native `Loan` set to repay from
  salary, and each installment reaches the Salary Slip through that loan's own
  repayment schedule. A site without the lending application saves the incident and
  raises no recovery; installing that application is what enables it. Do not
  duplicate the same event in `Movement Cost Recovery`.
- `Salis Payment Request` itself posts no General Ledger entry. **Create Payment**
  builds the target configured under **Payment Routing** in `Habitat Settings`;
  auto-submit also requires the app-wide GL gate. The shipped gates are off by default. Finance
  must validate the target and field map before using that action, and **Mark
  Paid** should follow evidence of the actual accounting payment.
- Cancelling an incident after its recovery carries a disbursed or repaid amount is
  refused. Reverse the accounting or payroll transaction through its
  own lifecycle first.

## Evidence of completion

- The vehicle shows the expected worst compliance state and next expiry.
- The incident, suspension, and write-off remain separate, linked records with
  their own evidence and actor history.
- The vehicle is `Stopped` only because of the submitted suspension.
- The write-off shows the derived authority tier and a different approving user.
- The payment request is `Approved by Finance`, with a Finance approver different
  from the requester and no linked payment document.
- No `GL Entry`, `Loan`, or `Additional Salary` was created by the exercise.

## Related links

- [Fleet and movement](fleet-movement.md)
- [Fuel operations](fuel.md)
- [Rental fleet](rentals.md)
