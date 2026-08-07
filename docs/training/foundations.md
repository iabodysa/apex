# Frappe Foundations

## Audience

Apex Desk operators and reviewers.

## Roles

Use the learner's operational role on a non-production site. The trainer needs
a role that can prepare scoped records, but must not elevate the learner.

## Duration

45 minutes.

## Workspace or route

Roles with an assigned workspace start there. A Desk role without a dedicated
workspace uses the exact Awesome Bar entry in the
[training role map](README.md#role-tracks). Use `/app/action-inbox` only for
pending work owned by the learner. Portal-only Drivers do not take this lesson.

## Documented against

Apex 2.1.2 on Frappe 15.

Before training, rehearse this lesson and the reset procedure on the exact
release revision that the cohort will use.

## Learning outcomes

The learner will be able to:

- navigate from a role workspace or mapped Awesome Bar entry to an authorized
  record;
- distinguish a master, transaction, child table, and system-written output;
- distinguish Save, Submit, an owned workflow action, and a handoff to another
  role;
- use Action Inbox, notifications, filters, reports, authorized export, and
  attachments;
- explain DocPerm and User Permission scope;
- switch between English and Arabic layouts; and
- protect personal-token links.

## Prerequisites

- A training account with the learner's roles.
- A non-production site with English and Arabic enabled.
- A private browser session.
- An approved temporary export location and deletion deadline when the role
  permits export.
- The site's own **Role Permissions Manager** (`/app/permission-manager`) for who may
  read, write or submit each document, and the [modules, workspaces, and routes
  reference](../reference/routes-workspaces.md).

## Demo records

For each learner role, the trainer prepares:

- one authorized Draft transaction marked `TRAINING`, editable only when the
  learner's role owns Write;
- when the role owns a workflow transition, one workflow-controlled record with
  a real open **Workflow Action** assigned to the learner;
- when the role does not own a workflow transition, one record waiting for the
  documented next role and a verified absence of an Action Inbox item for the
  learner;
- one trainer-viewable source transaction and linked system-written output;
- one trainer-verified notification linked to a training source;
- at least three authorized fictional records for filtered List practice;
- for a scoped role, one record outside the learner's Project, Building, or
  Company User Permission;
- for an unscoped role, one training record and an exact operation that the role
  does not own, rehearsed by the trainer to return a permission denial; and
- one sanitized image or PDF containing no personal or confidential data.

Do not use a production link or another person's personal-token link. If the
trainer demonstrates worker access, issue a fresh training link after the
baseline restore and never preserve it as evidence.

When the role owns a transition, generate the Workflow Action through the
source record's normal workflow; do not create a Workflow Action record
directly.

## Scenario

The learner receives an operational item, finds its source record, checks its
authorization, and adds safe evidence. The learner completes an owned action or
records the documented handoff when the next action belongs to another role.

## Core concepts

- A **master** is reusable data such as a Building, vehicle, or item.
- A **transaction** records an event such as a request, assignment, issue, or
  settlement.
- A **child table** stores lines inside its parent and is not an independent
  operating record.
- A **system-written output**, such as a ledger or snapshot, derives from a
  source transaction. Correct the source through its supported lifecycle; do
  not edit the output.

A Draft can be edited. Submission makes the record official. Cancellation
preserves history, and Amendment creates a corrected draft. A Workflow adds
role-owned states and actions; it does not replace document status.

## Instructor demonstration

1. Open the learner's workspace or mapped Awesome Bar entry and explain that
   navigation does not grant permission.
2. Open a master and a transaction with a child table. Use an authorized
   trainer account to show the linked system-written output when the learner
   cannot read it; never broaden the learner's role. Identify its source.
3. Use the Awesome Bar to open a List view. Add status, scope, and Modified
   filters, then open a report for the same area. Filters narrow authorized
   data; they do not widen access.
4. Show Export only when the learner's role exposes it and the trainer approved
   the temporary destination, columns, and retention period. A missing Export
   action is a valid permission checkpoint.
5. Open the Draft record. If the learner owns Write, demonstrate **Save**. If
   the role is read-only, use an authorized trainer account for the
   demonstration and show that the learner has no edit action. Explain that
   Submit creates an official record, while cancellation and amendment preserve
   history.
6. If the learner owns a workflow transition, open the workflow-controlled
   record and its real Workflow Action. Use only the action offered by the
   workflow. A workflow action can change state or submit the document; it is
   not interchangeable with Save.
7. If the learner owns no transition, open the prepared source, identify its
   state and documented next role, then show that Action Inbox has no item for
   that source. Do not create a substitute task or broaden the learner's role.
8. If the learner owns Write, attach the sanitized file to the Draft and show
   the timeline entry. For a read-only learner, prepare the attachment in
   advance and inspect it without changing the record.
9. In My Settings, change Language to Arabic, save, and reload. Confirm
   right-to-left layout, then restore English.
10. Explain that the full URL for a driver or worker personal-token portal is a
   credential. Never place it in screenshots, tickets, chat, email, browser
   recordings, logs, or training evidence. If a worker link is exposed, close
   the affected session, generate a fresh link with the displayed action, and
   notify the site administrator or security owner through your organization's
   credential-incident procedure. Confirm that the old link is rejected and the
   incident is recorded without the credential. If access must end, escalate to
   the site administrator for approved revocation because the form has no
   reviewed Disable or Set Expiry action.

## Learner exercise

1. Sign in with the training account and open the assigned workspace or mapped
   Awesome Bar entry.
2. Find the permitted Draft through the Awesome Bar or its List view.
3. Add status, scope, and Modified filters. Inspect three results and confirm
   the expected count.
4. If Export is present and authorized, export only the filtered rows and
   required columns, compare row counts, and place the file in the approved
   temporary location. If Export is absent, record that expected result and do
   not request a broader role.
5. If the role owns Write, add the sanitized attachment and Save, then confirm
   the record remains Draft. If the role is read-only, inspect the prepared
   attachment and confirm that no edit action is available.
6. Follow the branch prepared for the learner's role:
   - If the role owns a transition, open the real Workflow Action and inspect
     its source.
   - If the role owns no transition, open the prepared source directly and
     confirm that Action Inbox has no item for it.
7. Read the timeline and verify the current state. Apply only the assigned
   Workflow Action, or name the documented next role and handoff.
8. Refresh Action Inbox. Confirm that the completed Workflow Action is gone, or
   that the handoff-only source still has no action for the learner.
9. Check the related notification and confirm its source matches the record.
10. Switch to Arabic, verify right-to-left navigation and translated labels,
   then restore English.
11. Complete the permission-negative check below.

## Expected evidence

- The filtered List view, filter values, and inspected row count.
- For an authorized export: selected columns, matching row count, approved
  location, retention deadline, and deletion confirmation. Otherwise: the
  expected absence of Export.
- The Draft name, attachment filename, and timeline entry, plus either the
  saved Draft state or the expected read-only result.
- For an owned transition: the source state before and after the action, and
  Action Inbox no longer showing the completed Workflow Action after refresh.
- For a handoff-only role: the source state, documented next role, and expected
  absence of an Action Inbox item for that source.
- English and Arabic screenshots with all personal tokens and confidential
  values excluded.
- The exact permission-denied result from the negative check.

## Permission-negative check

- For a scoped role, the trainer gives the learner a direct link to the
  out-of-scope training record. The learner confirms it is absent from the List
  view and direct access is denied.
- For an unscoped role, the learner repeats the trainer-rehearsed operation that
  the role does not own on the prepared training record and records the
  permission denial.

Do not change roles, User Permissions, ownership, or URLs to make either check
pass. A known record name is not authorization.

## Troubleshooting

- **Workspace or page is missing:** compare roles with the routes reference;
  never grant a role only to reveal navigation.
- **Record is missing:** check filters and Project, Building, or Company User
  Permission.
- **Action differs from the prepared branch:** check document status, workflow
  state, role, and row scope. An owned transition must have its real Workflow
  Action; a handoff-only source must have no action for the learner.
- **Notification opens no action:** treat it as an alert, then inspect the
  source record and its current workflow.
- **Arabic remains left-to-right:** save Language in My Settings and reload.
- **Attachment is rejected:** use the trainer-provided safe file and record the
  displayed validation message; do not bypass file restrictions.

## Assessment

Pass when the learner completes the scenario without elevated access, explains
the four record types, distinguishes Save, Submit, an owned workflow action, and
a handoff, handles the Draft and export according to permission, filters
authorized records, produces safe evidence, and completes the applicable
permission-negative check.

## Reset

The authorized account removes the attachment while the record is an editable
Draft. Delete an unused Draft only when policy and permission allow it. Cancel a
submitted training transaction only when the trainer confirms no downstream
entry will be created.
Restore Language, filters, and assignments. Never delete submitted history or
alter the database. Remove any saved training filter. Delete an authorized
export at its approved deadline and record deletion without retaining the file.
Never export personal, payroll, identity, token, or financial data for practice.

## References

- **Role Permissions Manager** (`/app/permission-manager`)
- [Modules, Workspaces, and Routes](../reference/routes-workspaces.md)
- [Getting Started in Apex](lessons/getting-started.md)
- [Records and Workflows](lessons/records-and-workflows.md)
- [Search, Filter, and Export](lessons/search-filter-export.md)
