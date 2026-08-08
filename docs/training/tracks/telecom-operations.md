# Telecom Operations Track

[Back to training](../README.md)

## Outcome

Complete one company-scoped telecom cycle from contract and SIM custody to an
allocated Finance draft, with a clean handoff between roles.

## Roles

Run the track with separate **SIM Operations User** and **Finance Manager**
accounts. An **Internal Auditor** may review the result. Use **System Manager**
only for training administration.

## Guide sequence

1. Restore the Telecom baseline with [Trainer Setup and Reset](../trainer-setup.md).
2. Confirm the learner's Company scope with
   [Follow Work from Request to Proof](../foundations.md).
3. Complete the operating and Finance procedures in [Telecom](../telecom.md).
4. Use [Telecom troubleshooting](../../reference/troubleshooting.md#sim-state-looks-wrong)
   only if the resulting state or Cost Center is unexpected.

## Capstone

1. As SIM Operations User, create one submitted contract and two SIM Cards for
   the permitted Company.
2. On the first SIM, record **Assign to Employee → Transfer to Project → Return**.
   It must finish Available.
3. On the second SIM, record **Suspend while Available → Reactivate**, then assign
   it to the Project. This keeps the suspend/reactivate exercise independent of the
   transfer/return chain.
4. Correct one mobile number on its existing SIM Card, then use Telecom Control
   and the telecom reports to prove current custody, Cost Center, exception, and
   Company scope.
5. As Finance Manager, raise the period's draft Material Request and the draft
   Payment Entry allocated to the prepared submitted Purchase Invoice. Repeat the
   actions for the same period and confirm that no duplicate is created.

## Passing evidence

Show the submitted contract, both SIM identities, both valid custody chains, the
Employee and Project Cost Center snapshots, the in-place number correction, the
out-of-scope Company denial, and the two source-linked Finance drafts. A draft
Payment Entry is a handoff, not proof of settlement.

## Related links

- [Modules, workspaces, and routes](../../reference/routes-workspaces.md)
- [Scheduled automation](../../reference/automation.md)
