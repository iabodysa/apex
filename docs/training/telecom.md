# Telecom

[Back to training](README.md)

## Audience

SIM Operations Users and System Managers who operate telecom contracts, SIM
inventory, and custody. Finance reviewers inspect permitted contract data and
native billing drafts; they do not use Telecom Control.

## Outcome

Set up a telecom contract, register SIM cards, record each custody change, and
trace the result through the correct control page, form, and reports for the
learner's role.

## Prerequisites

- A non-production training site.
- Trainer-provided Company, telecom Supplier, Cost Center, Project, Employee,
  and non-stock service Item records.
- Company User Permission where the training role is company-scoped.
- [Telecom permissions](../reference/permissions.md#telecom-permissions).

## Record model

### Telecom Contract

One submitted **Telecom Contract** represents one supplier agreement for one
Company. It stores the contract dates, billing frequency, recurring amount,
currency, and optional Project, Cost Center, and service Item.

The server derives its state:

- Draft before submission;
- Active while a submitted contract is in force;
- Expired when validation finds that a submitted contract has passed its end
  date; and
- Terminated when cancelled.

One supplier may have several contracts. The SIM count on each contract is
recalculated from the SIM cards linked to it.

### SIM Card

**SIM Card** is the managed telecom asset. It belongs to one submitted Telecom
Contract and carries the mobile number, optional ICCID, plan, and current
custody projection.

The mobile number remains editable on the same SIM Card. Apex does not ship a
**Mobile Number** or **SIM Number Assignment** DocType, and a number correction
must not create a second SIM record.

### SIM Custody Assignment

Each submitted **SIM Custody Assignment** is one custody event:

- **Assign** gives an Available SIM to an Employee or Project.
- **Transfer** moves an Assigned SIM to another Employee or Project.
- **Return** releases an Assigned SIM back to Available.
- **Suspend** pauses an Available or Assigned SIM.
- **Reactivate** restores a Suspended SIM to its prior assigned or available
  state.

Transfer is an action in this record. Apex does not ship a separate **SIM
Transfer Request**.

The event captures the previous holder and freezes the Employee or Project Cost
Center. The SIM Card's current holder, state, effective Cost Center, assignment,
and assignment date are rebuilt from submitted events. Correct history through
the supported cancel or amend lifecycle; do not edit projected fields.

## Operating path

1. Create and submit the Telecom Contract.
2. Create each SIM Card under that contract.
3. With a SIM Operations User or System Manager account, open **Telecom
   Control** from the Custody and Costs workspace.
4. Filter by Company, Supplier, contract, Project, Cost Center, or state.
5. Open a SIM drawer and use the action allowed by its current state.
6. Review the resulting custody history and current projection.
7. Use the telecom reports to review current custody, multiple-SIM holders,
   contract distribution, expiry, cost allocation, and exceptions.

Telecom records belong to **Logistay**, which ships its own workspace. They are
also exposed through the Custody and Costs workspace and the Telecom Control
page; there is no separate SIM module.
Page access and visible buttons remain subject to the
[telecom permission reference](../reference/permissions.md#telecom-permissions).
Finance Manager has read-only contract access and no Telecom Control Page role;
finance reviews the contract form, reports, and any native draft it may create
through its separate target-DocType permission.

## Billing drafts

A submitted contract offers **Raise Purchase Request**, which creates or
returns one draft native **Material Request** of type Purchase for the contract
and billing period. The contract needs a service Item. The action requires
create permission, records the draft on the contract, and returns the existing
draft when repeated for the same period.

Do not use **Raise Payment Order** in production or training. It currently
saves an unreferenced Supplier Payment Entry: an unallocated supplier advance
draft, not an ERPNext Payment Order and not settlement of a supplier bill.
`reference_no` is descriptive and does not allocate the payment.

Finance uses the native payable path instead: create the Purchase Order first
when site policy requires it, approve the Supplier Purchase Invoice for the
telecom period, then create a Payment Entry whose References table allocates the
amount to that Purchase Invoice. Native approval and submission remain with
Finance.

## Exercise

1. Create and submit a `TRAINING` Telecom Contract for the demo Supplier.
2. Register two SIM Cards with fictional mobile numbers under that contract.
3. Assign the first SIM to the demo Employee.
4. Transfer it to the demo Project and confirm the Cost Center snapshot.
5. Edit the mobile number on the same SIM Card.
6. Return the SIM and confirm its current state is Available.
7. Open the **SIMs in Custody** shortcut on the Logistay workspace, then
   **Employees Holding Multiple SIMs** and **SIM Exceptions**, to explain why the
   training rows do or do not appear.

## Verification

The learner can show that:

- the contract, SIM Card, and custody event have distinct purposes;
- the number change kept the same SIM Card and timeline;
- every custody change produced a submitted event;
- the SIM projection matches the latest submitted event;
- Company scope limits the records shown; and
- the Material Request is only a procurement draft and Supplier payment follows
  the native invoice-allocation path.

## Cleanup and data safety

Use fictional numbers and no real ICCID. Reverse or cancel training custody
events through the normal lifecycle and in dependency order. A System Manager
may remove unused training masters after linked records are cleared. Do not
delete submitted custody history, edit projection fields, use **Raise Payment
Order**, or create finance documents on production for practice.
