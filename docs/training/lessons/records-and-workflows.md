# Approve a Fuel Request with Separation of Duties

[Back to foundations](../foundations.md)

## Business outcome

Authorize a valid fuel request while preserving the requester, approver, Project scope, and
decision history needed for operational control.

## Journey and roles

```text
Fuel Request: Pending
  -> Fleet Manager reviews another user's request
  -> Approve
  -> Fuel Request: Approved
```

- A **Fleet Supervisor** creates the fictional `Fuel Request`.
- A different **Fleet Manager** or **Fleet Project Manager** reviews it.

The trainer prepares an active vehicle, driver, Project, fuel platform, and monthly
`Fuel Quota`. The requested litres must fit inside the remaining training quota.

## Review and decide

1. Sign in as the approver and open the pending `Fuel Request` from **Action Inbox**.
2. Confirm that **Requested By** names another user. Do not approve your own request.
3. Compare the vehicle, driver, Project, request date, requested litres, fuel platform, and
   linked quota with the trainer's evidence.
4. Record the quota's current consumed litres before the decision.
5. Choose **Approve** only when the source and scope agree. Choose **Reject** when they do not.
6. Reopen the request and inspect its timeline and actor fields.
7. Confirm that the approved request is ready for fulfilment but is not yet a completed fuel
   issue.

Do not type a status, edit a generated ledger, or use another user's account to manufacture
an approval.

## Expected state and evidence

For the approval path, the learner can show:

- the request moved from **Pending** to **Approved**;
- **Requested By** and **Approved By** name different users;
- vehicle, driver, Project, litres, platform, and quota match the source evidence;
- the decision appears in the timeline;
- the approval task no longer waits in **Action Inbox**; and
- quota consumption has not changed yet.

The business result is an authorized request ready for controlled fulfilment. Completing the
request and reconciling fuel are covered in [Control Fuel from Quota to Claim](../fuel.md).
