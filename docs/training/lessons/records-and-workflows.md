# Records and Workflows

## Audience

Operators who create records and reviewers who approve, submit, cancel, or
amend them.

## Outcome

Recognize Frappe record types and choose the correct action for each lifecycle
state.

## Prerequisites

- Completion of [Getting Started in Apex](getting-started.md).
- A non-production training site.
- A trainer-selected DocType allowed by the learner's role.
- The **Role Permissions Manager** (`/app/permission-manager`).

## Core concepts

A **master** is reusable data such as a building, vehicle, or item. A
**transaction** records an event such as an assignment, request, issue, or
settlement. A **child table** stores lines inside its parent record and is not an
independent operating record.

A standard submittable record follows Frappe's document lifecycle:

1. **Draft** can be edited.
2. **Submitted** is the official record.
3. **Cancelled** preserves history after reversal.
4. **Amend** creates a corrected draft linked to the cancelled record.

A **Frappe Workflow** adds controlled states and role-based actions. Workflow
state and document status are related but not interchangeable. Use the action
shown by the form; do not bypass a required review with direct database changes.

System-written ledgers and snapshots are outputs. Operators work through the
source transaction, not the generated record.

## Exercise

1. On the training site, open the DocType selected by the trainer.
2. Create a record using only realistic training values and add `TRAINING` to a
   suitable title or description field.
3. Save it as Draft and note which fields remain editable.
4. Identify whether the form offers **Submit** or a workflow action.
5. Use the approved action only when the trainer confirms the record and the
   learner's role is responsible for that step.
6. Open the timeline and identify the creator, changes, and workflow events.

## Verification

The learner can explain:

- why master data and transactions have different purposes;
- the difference between Save, Submit, a workflow action, Cancel, and Amend;
- why a submitted record is not corrected by deleting its history;
- which role owns the next action by checking the canonical permission reference
  and the action available on the form.

## Cleanup and data safety

Never practise on production. Delete an unused Draft only when policy and
permission allow it. Cancel a submitted training record through its normal
lifecycle; do not delete it or edit the database. Ask the trainer to clean up
records when cancellation could trigger accounting, stock, payroll, or other
downstream effects.
