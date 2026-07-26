# Telecom Operations Track

## Audience

SIM Operations Users and System Managers responsible for telecom contracts and
SIM custody, plus finance reviewers who inspect contracts and native drafts
outside Telecom Control.

## Outcome

Trace one telecom agreement from contract setup through SIM registration,
custody, exception review, and the native procurement handoff.

## Prerequisites

- A non-production training site.
- A training Company, Supplier, service Item, Cost Center, Project, Employee,
  and two fictional SIM numbers.
- Company User Permission for the operating account where scope applies.
- Separate operating and finance accounts for maker-checker practice.

## Learning path

1. [Frappe Foundations](../foundations.md)
2. [Telecom](../telecom.md)
3. [Settings and Desk Pages](../settings.md)
4. [Telecom permissions](../../reference/permissions.md#telecom-permissions)
5. [Telecom troubleshooting](../../reference/troubleshooting.md#sim-state-looks-wrong)

## Practice checkpoint

1. Create and submit one `TRAINING` Telecom Contract with a service Item.
2. Create two SIM Cards under the contract.
3. Assign the first SIM to the training Employee.
4. Assign the second SIM to the training Project.
5. Transfer the first SIM to the Project, then return it.
6. Correct its mobile number on the same SIM Card.
7. With the SIM Operations User or System Manager account, use Telecom Control
   and the telecom reports to verify current custody, contract totals, multiple
   holdings, expiry, cost allocation, and exceptions.
8. With the authorized finance account, open the Telecom Contract form and
   raise a purchase request for one training billing period. Confirm it is a
   draft Material Request. Finance does not enter Telecom Control.
9. Repeat **Raise Purchase Request** for the same period and confirm it returns
   the existing Material Request instead of creating a duplicate.
10. Do not use **Raise Payment Order**. Identify the approved native path:
    Purchase Order when site policy requires it, Supplier Purchase Invoice for
    the billing period, then Payment Entry allocated to that invoice.

## Verification

The trainee can identify:

- Telecom Contract as the commercial source;
- SIM Card as the editable asset record;
- SIM Custody Assignment as the immutable event history;
- Company as the row-scope boundary;
- Employee or Project Cost Center captured at the custody event; and
- Material Request as the procurement handoff rather than evidence of a bill or
  payment; and
- the Finance-owned invoice and allocated-payment steps that follow.

## Cleanup and data safety

Delete the draft Material Request only through its native form and with finance
approval. Cancel training custody events newest first, then clear dependent SIM
and contract records through normal Frappe actions. Use fictional numbers and
no real ICCID. Never use **Raise Payment Order**, submit a training payment,
alter live custody, or remove submitted history directly.
