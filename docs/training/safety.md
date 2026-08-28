# Safety Operations

[Back to training index](README.md)

## Outcome

Record a periodic Building safety round, preserve the evidence behind its result, and
route actionable findings to maintenance without confusing them with incidents or
licence work.

## Intended role

A **Safety Officer** prepares `Safety Round` and `Safety Task Execution` drafts. An
**Accommodation Manager** or **Resident Supervisor** reviews and submits them. An
**Internal Auditor** reviews the resulting evidence but does not alter it.

## Before starting

- Use a disposable training site with a fictional Building and at least one Room.
- Prepare an active `Safety Task Catalog` item for the Building and chosen cadence.
- Use separate Safety Officer and submitting-role accounts.
- Prepare a sanitized photo if the task requires evidence or the finding concerns
  Security.

Never create a false production incident, finding, or licence date for practice.

## Exercise: record and escalate one finding

1. As Safety Officer, create and save a draft `Safety Round` for the Building, date,
   and cadence.
2. Create a linked `Safety Task Execution`. Set the result to **Poor**, add a clear
   note, and add one finding with a description, Room, issue type, severity, and
   priority. Attach the training photo when required.
3. Sign in as Accommodation Manager or Resident Supervisor. Review the round and its
   execution, then submit the round. Submission also submits its draft executions.
4. Confirm the round result is **Needs Attention**.
5. Open the generated `Maintenance Request` link or links and confirm they point back
   to the execution. Find the corresponding immutable row in `Safety Finding Ledger`.

## Decisions and exceptions

- The worst execution result controls the round: **Not Done** makes it **Fail**;
  otherwise **Poor** makes it **Needs Attention**; all other results make it **Pass**.
- A normal second round for the same Building, date, and cadence is blocked. Select
  **Is Re-inspection** only for a genuine follow-up.
- A failed task marked as requiring evidence cannot be submitted without a photo.
  An actionable Security finding also requires photo evidence.
- The **Safety Checklist** portal maps **Pass** to **Good**, **Issue** to **Poor**, and
  **Fail** to **Not Done**. It accepts only the tasks the operator rates, so operations
  must rate every displayed task before submission.
- Safety Officer can open the portal but cannot submit `Safety Task Execution`; the
  officer must prepare drafts in Desk and hand them to a submitting role. The portal
  also cannot attach finding rows or evidence photos, so use Desk for those cases.
- Use `Safety Incident` for an actual incident or near miss. Closing it requires
  resolution notes. Use `Building License` for regulatory issue and expiry dates.
- `Safety Inspection Report` is historical and deprecated. Use `Safety Round` for new
  periodic work.
- Never edit `Safety Finding Ledger`. Cancelling a round creates reversal evidence.

## Evidence of completion

Show the submitted round and execution, the derived overall result, the finding and
photo where required, the generated maintenance link, and the matching
`Safety Finding Ledger` row.

## Related links

- [Maintenance operations](maintenance.md)
- [Safety Operations track](tracks/safety-operations.md)
- [Background follow-up](settings.md#background-follow-up)
