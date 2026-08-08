# Telecom in Logistay

[Back to training](README.md)

## Outcome

Bring a telecom agreement and its SIM inventory under control, keep custody and
cost ownership current, and hand each billing period to Finance through the
correct native documents.

## Intended role

- A **SIM Operations User** creates Telecom Contracts, SIM Cards, and submitted
  SIM Custody Assignments for an allowed Company. This role operates
  **Telecom Control**.
- A **Finance Manager** reviews telecom records and reports, raises authorized
  procurement and payment drafts, and completes the native accounting process.
  Finance does not have access to Telecom Control.
- An **Internal Auditor** has read and report access. A **System Manager** is the
  administrative fallback, not the routine operator.

A SIM Operations User sees only Companies granted through Company User
Permission. A user with no allowed Company sees no telecom rows.

## Before starting

- Use a disposable training site and fictional mobile numbers and ICCIDs.
- Prepare one Company, telecom Supplier, service Item, contract Cost Center,
  Project, and active Employee in the same Company.
- Give the Project a Cost Center. For the Employee exercise, configure an
  Employee payroll Cost Center, a Department payroll Cost Center, or a Company
  default Cost Center.
- Use a SIM Operations User with the training Company permission and a separate
  Finance Manager account with the required native document permissions.
- For the payment handoff, prepare one submitted, outstanding Purchase Invoice
  for the same Company and Supplier. Apex does not create that invoice from the
  telecom contract.

## Realistic end-to-end exercise

1. From **Logistay**, create a **Telecom Contract** for the training Company and
   Supplier. Enter the contract period, billing frequency, recurring amount,
   currency, Cost Center, Project, and service Item, then submit it.
2. Create two **SIM Card** records under the submitted contract. Use distinct
   fictional mobile numbers and ICCIDs and confirm that the contract's SIM Count
   becomes two.
3. Open **Custody and Costs > Telecom Control** (`/app/telecom-control`), filter
   to the training Company, and open the first SIM.
4. Assign the first SIM to the training Employee. Open the submitted **SIM
   Custody Assignment** and confirm its Employee Cost Center and Effective Cost
   Center snapshots.
5. Assign the second SIM to the training Project and confirm that its Project
   Cost Center becomes the SIM's current Cost Center.
6. Transfer the first SIM to the Project, then return it. Confirm that each
   action created a submitted custody event and that the SIM now reads
   **Available**.
7. Correct the first SIM's mobile number from Telecom Control. Confirm that the
   same SIM Card remains in place and its custody history is unchanged.
8. Review **Employees Holding Multiple SIMs**, **SIM Exceptions**, and
   **Telecom Contract Expiry** from Logistay. Use **Telecom Cost Allocation** to
   review recurring contract commitment by the contract's Cost Center.
9. Sign in as the authorized Finance user. On the submitted contract, choose
   **Billing > Raise Purchase Request**, enter a `YYYY-MM` billing period, and
   open the resulting draft **Material Request**. Confirm that it is a Purchase
   request for the service Item; it is not an invoice or a payment.
10. After the matching Purchase Invoice is submitted and remains outstanding,
    choose **Billing > Raise Payment Entry**, use the same billing period, and
    select that invoice. Open the draft **Payment Entry** and confirm that its
    References table allocates an amount to the selected Purchase Invoice.
    Finance reviews and submits the native document under the site's approval
    rules.
11. Repeat each billing action for the same contract, period, and document type.
    Confirm that Apex returns the recorded document instead of creating a
    duplicate.

## Decisions and exceptions

- **SIM Card is the source of truth for the current mobile number.** Correct the
  number on that record. Apex ships no separate **Mobile Number** or **SIM Number
  Assignment** record, so a number correction does not require a second SIM.
- **SIM Custody Assignment** records actions. Assign starts from Available;
  Transfer and Return start from Assigned; Suspend starts from Available or
  Assigned; Reactivate starts from Suspended. Lost and Terminated are retirement
  events and require a reason. Do not edit the SIM's projected status or current
  holder fields.
- Employee custody must stay within the SIM's Company. On Assign or Transfer,
  Apex freezes the effective Cost Center on the event. The Employee payroll Cost
  Center takes precedence, followed by the Department payroll Cost Center and
  the Company default. Project custody uses the Project Cost Center. Later master
  edits do not rewrite that history.
- An assigned SIM with no resolved Cost Center appears in **SIM Exceptions**.
  Correct the source master and record the appropriate next custody action; do
  not overwrite the historical snapshot.
- **Raise Purchase Request** needs a service Item and Create permission on
  Material Request. **Raise Payment Entry** needs Create permission on Payment
  Entry and a submitted, outstanding Purchase Invoice for the same Company and
  Supplier. The allocation comes from that invoice, not from a copied contract
  amount.
- Both billing actions create drafts. A draft Payment Entry is awaiting Finance
  approval; it is evidence of a handoff, not settlement or a General Ledger
  posting.

## Evidence of completion

The learner can show:

- one submitted Telecom Contract with the expected Company, Supplier, billing
  data, service Item, and SIM Count;
- two SIM Cards whose current status, holder, and Cost Center agree with their
  latest submitted custody events;
- an Employee assignment with its frozen Employee and Effective Cost Centers;
- the same SIM Card name before and after the mobile-number correction;
- only the permitted Company's rows in Telecom Control and telecom reports;
- one draft Material Request for the billing period; and
- one draft Payment Entry whose References row names the submitted Purchase
  Invoice and carries a positive allocation.

## Related links

- [Telecom Operations track](tracks/telecom-operations.md)
- [Costs and Leasing](costs.md)
- [Modules, workspaces, and routes](../reference/routes-workspaces.md)
