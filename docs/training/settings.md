# Settings and Desk Pages

[Back to training](README.md)

## Audience

Site administrators and designated process owners who configure Apex or support
Desk pages.

## Outcome

Choose the correct settings record, make a controlled non-production change,
and distinguish configuration, navigation, permission, and automation.

## Prerequisites

- Administrator access to a non-production site.
- An approved before-and-after value for the setting being tested.
- Separate training accounts for any role or scope checks.
- Roles and rights: **Role Permissions Manager** (`/app/permission-manager`).
- [Modules, workspaces, and routes](../reference/routes-workspaces.md).

## Configuration records

Use the narrowest setting that owns the behavior:

- **Apex Settings** controls the General Ledger posting gate and retention
  windows for snapshots.
- **Habitat Settings** controls accommodation defaults, custody integration,
  safety thresholds, notifications, handover controls, housing contact details,
  and optional passport scanning.
- **Salis Settings** controls fleet defaults, alert thresholds, approvals,
  driver access, boarding behavior, and optional web push.
- **Apex Integration Settings** records external-frontend and messaging-gateway
  configuration. Its integration switch and origin list are descriptive; they
  do not modify server CORS or grant API access. Follow the
  [integration guide](../administration/integration.md).
- **Payment Routing Settings** is not production-ready from the setup-wizard
  choice alone. Keep `Payment Entry` as the target, keep target auto-submit off,
  and do not use **Create Payment** until Finance has reviewed and validated a
  complete field map on the target site. Do not select `Payment Order` or a
  custom target in this release.
- **Salary Deduction Policy** gates operational recovery through payroll. It
  ships inactive and must not be enabled without the required legal, HR, and
  management review.
- **Driver Portal Theme** controls the appearance shared by the worker and
  driver mobile experiences.

Changing a Single affects the site, not one user. Record the old value and test
the effect before using the same change in production.

## Personal portal access

**Masar Worker Token** is an operational credential record, not a general
setting. After Save, use whichever **Issue Link and QR** or **Rotate Link and
QR** action the form displays. Either action generates a fresh link and
invalidates any previous link. The label depends on permission-level-one token
visibility, not lifecycle state. **Enabled**, **Expires On**, and the credential
fields are read-only, and the form exposes no reviewed Disable or Set Expiry
action.

If a link is exposed, close the affected session, generate a fresh link with
the displayed action, and follow your organization's credential-incident
procedure with the site administrator or security owner. Confirm that the old
link is rejected and the incident is recorded without the credential. If
access must end, escalate to the site administrator for approved revocation.
Never edit credential fields or the database to work around the missing form
actions.

Worker and driver bindings remain distinct even though both experiences use one
frontend build. The current Desk UI has no reviewed driver-link issuance action,
so driver access and walkthroughs remain optional and unavailable. Do not work
around that boundary with direct API calls or hand-built URLs. Temporary
Workers cannot receive a worker link until the daily linking flow connects them
to an Employee. See
[Driver and Worker Portals](portals-masar-driver.md).

## Desk pages

A Frappe Page is a task-focused screen over existing DocTypes. Use it for the
workflow it presents, then open the source record when full history or form
actions are needed.

The canonical list of shipped pages, workspaces, shortcuts, and public routes
is maintained in the
[modules, workspaces, and routes reference](../reference/routes-workspaces.md).
Do not grant a role merely to reveal a page. Page visibility does not replace
DocPerm, User Permission, workflow, or server-side scope.

**Action Inbox** is the signed-in user's cross-module worklist. An item appears
because a workflow or assignment expects that user; the page itself does not
grant the next action.

## Background processing

Use the [scheduled automation reference](../reference/automation.md) to identify
the exact callable, cadence, effect, and gate. Check **Scheduled Job Log** and
the affected source record before rerunning a job.

An empty run can be correct when no source record qualifies, an idempotency key
already exists, or a feature switch is off. Do not infer failure from an
unchanged dashboard alone.

## Change path

1. Identify the business behavior and its owning settings record.
2. Capture the current value and expected result.
3. Change one field on the non-production site.
4. Test with the affected operational persona.
5. Check source records and logs, not only navigation.
6. Restore the baseline or record the approved new value.

## Exercise

1. Record the current **Driver Portal Theme** and accent color.
2. Change only the accent color on the training site.
3. Open the training worker experience and confirm the new appearance.
4. Check the driver experience only when a later release provides reviewed
   Desk issuance.
5. Find one relevant background task in the
   [automation reference](../reference/automation.md) and identify its gate
   without running it.
6. Restore the original theme value.

## Verification

The learner can:

- select the settings record that owns a stated behavior;
- explain why a Page or workspace does not grant record access;
- locate a scheduled task without copying its inventory into local notes;
- show that shared appearance does not grant another portal identity; and
- prove the exercise value was restored.

## Cleanup and data safety

Never practise with production feature switches, retention windows, payment
routing, salary deductions, messaging credentials, or personal access links.
Restore training settings after the exercise. Do not run a scheduled task until
its writes, deduplication behavior, and downstream effects are understood.
