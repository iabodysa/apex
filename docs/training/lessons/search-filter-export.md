# Search, Filter, and Export

## Audience

Desk users who need to find, review, or share operational data.

## Outcome

Build a focused List view, verify its scope, and export data safely when the
role permits it.

## Prerequisites

- Completion of [Getting Started in Apex](getting-started.md).
- Read access to a DocType used in the learner's track.
- A non-production training site for export practice.
- The [permissions and role reference](../../reference/permissions.md).

## Core concepts

The **Awesome Bar** finds named DocTypes, pages, and records. A **List view**
filters and sorts one DocType. A **Report** answers a defined business question.

Filters narrow the records already allowed by DocPerm and row scope; they never
widen access. Export creates a separate copy of operational data and therefore
needs the same care as the source system.

## Exercise

1. Open a List view used in the learner's role.
2. Add a status filter and one scope filter available on that DocType, such as
   Project or Building.
3. Add a Modified date filter that limits the result to the training period.
4. Sort the result and inspect three records to confirm the filter is correct.
5. Save the filter as **Training - My Active Records** if the site offers saved
   filters.
6. If the trainer authorizes export and the role exposes it, export only the
   filtered rows and required columns.
7. Compare the exported row count with the filtered List view.

## Verification

The learner can show:

- the active filters and their expected scope;
- that no unexpected record outside the account's assigned scope appears;
- matching row counts for the List view and authorized export;
- the approved location and retention period for the downloaded file.

## Cleanup and data safety

Remove the saved training filter when it is no longer useful. Delete the
downloaded file after verification. Never export personal, payroll, identity,
token, or financial data for practice. If unexpected records appear, stop and
report the scope issue instead of opening or sharing them.
