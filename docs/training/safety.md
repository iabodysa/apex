# Safety Operations

[Back to training index](README.md)

## Audience

Accommodation Managers and Resident Supervisors who submit rounds, Safety
Officers who prepare or review records, and Internal Auditors who review
evidence.

## Outcome

Record a current `Safety Round`, trace failed checks to maintenance, and keep
incidents and licence follow-up separate from routine inspections.

## Prerequisites

- A non-production training site.
- A training Building with at least one Room.
- An active `Safety Task Catalog` item scoped to that Building and cadence.
- A training account that can submit `Safety Task Execution`.
- The [safety permission reference](../reference/permissions.md#safety-permissions).

## Operating model

Use `Safety Round` and its linked `Safety Task Execution` records for new
periodic inspections.

| Record | Operational purpose |
|---|---|
| `Safety Task Catalog` | Reusable check, cadence, priority, scope, and evidence rule. |
| `Safety Round` | Submitted Building-and-cadence grouping for one period. |
| `Safety Task Execution` | Result, evidence, findings, and maintenance links for one check. |
| `Safety Incident` | Actual incident or near miss, separate from a routine round. |
| `Building License` | Submitted regulatory record and renewal dates. |
| `Audit Remediation Plan` | Client finding, owner, deadline, and remediation actions. |

`Safety Inspection Report` is retained only as a deprecated historical surface.
Do not create it for new work.

`Safety Finding Ledger` is system-written when a round is submitted. Read it
for audit history; do not edit or recreate its rows.

## Operational flow

1. Maintain `Safety Task Catalog` records. Set cadence, Building scope,
   priority, instructions, and whether photo evidence is required.
2. For a routine mobile round, open the Safety Checklist portal, select a
   Building, and rate every displayed task. The portal creates one submitted
   `Safety Round` per due cadence and one submitted `Safety Task Execution` per
   rated task.
3. Portal verdicts map to execution results: **Pass** becomes **Good**,
   **Issue** becomes **Poor**, and **Fail** becomes **Not Done**. A round becomes
   **Fail** when any execution is **Not Done**, **Needs Attention** when any
   execution is **Poor**, and **Pass** otherwise.
4. For a failed task that needs evidence or detailed findings, use Desk. Save a
   draft `Safety Round`, create its linked `Safety Task Execution`, attach the
   photo, and add each finding. A finding needs a Room and issue type to create
   a `Maintenance Request`. Submit the executions first, then submit the round.
5. A **Poor** or **Not Done** execution creates one summary
   `Maintenance Request` when the Building has a Room. Each actionable finding
   can also create its own room-specific request. Back-links prevent duplicate
   creation.
6. A normal second round for the same Building, date, and cadence is blocked.
   Use **Is Re-inspection** only for a genuine follow-up.
7. Record an actual event in `Safety Incident`, including immediate action and
   severity. Closing it requires resolution notes.
8. Submit `Building License` records with issue and expiry dates. Native Frappe
   Notifications handle expiry notices; a daily job updates the stored status.
   Coverage scans, overdue tasks, and remediation deadlines are described in
   the [automation reference](../reference/automation.md).
9. Accommodation Managers and Resident Supervisors can review **Safety Map**.
   Safety Officers and Internal Auditors use the reports and records their
   DocPerms allow, including **Safety Open Findings**, **Safety Task Compliance
   Summary**, and **Audit Remediation Status** where granted.

Portal access and its exact role gate are listed in the
[route and workspace reference](../reference/routes-workspaces.md#served-portal-routes).

## Current boundaries

- The `Safety Officer` role can prepare records but cannot submit
  `Safety Task Execution`, and the current Safety Checklist route does not admit
  that role.
- Safety Map admits System Manager, Accommodation Manager, and Resident
  Supervisor only.
- The portal does not capture an evidence photo or finding rows. A failed task
  whose catalog requires evidence will reject the portal submission; use Desk.
- The portal allows a partially rated list. Operators must rate every displayed
  task before submitting.
- `Safety Inspection Report` is deprecated and no workspace links it. Use
  `Safety Round` for new work.

## Non-production exercise

1. Ask the trainer for an isolated Building and a due training task that does
   not require photo evidence.
2. With the Safety Officer account, prepare a draft `Safety Round` and linked
   `Safety Task Execution` in Desk. Record **Poor** and a concise note, then hand
   the records to the submitting role.
3. With an Accommodation Manager or Resident Supervisor account, review and
   submit the execution, then submit the round.
4. Open the submitted `Safety Round` and linked `Safety Task Execution`.
5. Verify the round is **Needs Attention** and the execution links to a summary
   `Maintenance Request`.

## Verification

The learner can show:

- one submitted Round per cadence and its linked executions;
- the expected overall result from the worst execution status;
- the linked Maintenance Request for the failed training task;
- the difference between a Safety Round and a Safety Incident;
- why new work must not use `Safety Inspection Report`.

## Cleanup and data safety

Run this exercise only on an isolated training Building. Generated rounds,
executions, alerts, maintenance requests, and ledger rows may be linked.

Let the trainer reverse the scenario in dependency order or reset the disposable
site. Use normal cancellation actions for the linked execution and round
records, and handle generated maintenance records separately. Preserve `Safety
Finding Ledger` originals and reversal rows. Never delete official incident,
licence, or audit evidence for practice.
