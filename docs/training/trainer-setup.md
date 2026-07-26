# Trainer Setup and Reset

Use this procedure only on a disposable, non-production site. It prepares one
repeatable dataset without copying operational records, credentials, or
attachments.

## Outcome and duration

Allow 90 minutes for provisioning and 20 minutes for a reset rehearsal. The
result is a clean baseline that a trainer can restore before each cohort.

## Prerequisites

- A dedicated site with outbound email, webhooks, payment connections, and
  production integrations disabled.
- A site administrator used only for provisioning, backups, and reset.
- An encrypted backup location with access limited to training administrators.
- The [permissions](../reference/permissions.md) and
  [routes and workspaces](../reference/routes-workspaces.md) references open
  during setup.

## Build the common baseline

1. Create **Apex Training Company** with abbreviation **ATC**. Do not connect it
   to production bank accounts, Suppliers, inboxes, or integrations.
2. Create **Training North** and **Training South** Projects with matching Cost
   Centers. Create **Training Campus**, then **Training Residence North** and
   **Training Residence South** Buildings. Generate one Room with two Beds in
   each Building.
3. Create fictional Employees named **Training Worker North** and **Training
   Worker South**. Do not use real identifiers, phone numbers, dates,
   addresses, photos, signatures, or emergency contacts.
4. Prepare the [Frappe Foundations](foundations.md) fixtures for every scheduled
   Desk learner role: one authorized Draft that is editable only when the role
   owns Write, one trainer-viewable source and linked system-written output,
   one trainer-verified notification, three authorized List records, and one
   sanitized attachment.
5. For a role that owns a workflow transition, prepare a workflow-controlled
   source with a real open Workflow Action assigned to the learner. Generate it
   through the source workflow, not by inserting a Workflow Action directly.
   For a role with no owned transition, prepare a source waiting for the
   documented next role and verify that no Action Inbox item exists for the
   learner.
6. For a scoped role, add one record outside its Project, Building, or Company
   User Permission. For an unscoped role, choose one exact operation the role
   does not own on a training record and rehearse the resulting permission
   denial.

The baseline intentionally contains no Masar Worker Token row. Do not create
one before the baseline backup.

## Add the chosen track overlay

Prepare only the overlays needed for the scheduled cohort:

- **Housing:** one demo resident and assignment, a Resident Request, a
  Maintenance Request, a safe draft Maintenance Work Order created by System
  Manager, a Cleaning Log checkpoint, a non-serialized Custody Article with
  positive training stock, and one Utility Account per Building.
- **Safety:** an active Safety Task Catalog item for the training Building and
  cadence, plus a draft Safety Round and linked Safety Task Execution.
- **Fleet:** two fictional driver Employees and active Salis Drivers, one active
  owned vehicle and assignment, a training Transport Request, draft Route Plan
  and Dispatch Trip, and a Fuel Platform. Add a separate rented vehicle linked
  to a training Supplier and Rental Office, then prepare a closed period whose
  Rental Accrual Ledger rows were generated normally.
- **Telecom:** a training Supplier, non-stock service Item, Telecom Contract,
  and two available fictional SIM Cards. Leave ICCID blank and create no
  payment or purchase document.
- **IT:** an Employee eligible for worker access, the current Driver Portal
  Theme values, and the role-specific settings and Foundations fixtures used by
  the support exercise. Issue no worker link until after each restore.

## Accounts, scope, and handoffs

Create separate logins for every learner role. Never combine maker, checker,
trainer administration, and finance review.

- Give each Resident Supervisor a User Permission for only Training Residence
  North or Training Residence South.
- Give each Fleet Project Manager or Fleet Supervisor a User Permission for
  only Training North or Training South.
- Give each SIM Operations User a Company User Permission for Apex Training
  Company.
- Create distinct maker and checker accounts for each approval exercise. Sign
  out at handoff; never lend the checker account.
- Grant only the roles listed in the canonical
  [role charters and permission matrices](../reference/permissions.md#role-charters).
  A workspace or Page entry does not replace record permission.

Test each scoped account. The North account must find North records but not
South records. For every unscoped learner role, repeat the selected denied
operation and confirm its permission error. Treat unexpected access as a setup
failure, not a reason to add a broader role.

## Baseline backup and restore rehearsal

Use an explicit disposable site name. Replace the backup directory with an
existing absolute directory restricted to training administrators. After the
common baseline, chosen overlays, and scope checks pass, create the backup
before issuing any personal link:

```bash
set -eu
umask 077
test -d /absolute/restricted/path
test -w /absolute/restricted/path
bench --site <training-site> set-maintenance-mode on
bench --site <training-site> backup --with-files \
  --backup-path /absolute/restricted/path
```

Read the successful backup summary. Record its exact absolute database,
public-files, private-files, and site-config paths in the restricted checklist,
then verify them:

```bash
set -eu
test -f "/absolute/restricted/path/<database-backup>"
test -f "/absolute/restricted/path/<public-files-backup>"
test -f "/absolute/restricted/path/<private-files-backup>"
test -f "/absolute/restricted/path/<site-config-backup>"
```

Before each restore, remove cohort-created attachments through the owning
document and native File lifecycle. Native file restore overlays the existing
public and private trees; it does not remove extra files. If every cohort file
cannot be accounted for, recreate the disposable site or restore an
infrastructure snapshot that replaces the database and both file trees.

Rehearse the native restore with maintenance left on:

```bash
set -eu
test -f "/absolute/restricted/path/<database-backup>"
test -f "/absolute/restricted/path/<public-files-backup>"
test -f "/absolute/restricted/path/<private-files-backup>"
bench --site <training-site> set-maintenance-mode on
bench --site <training-site> restore \
  "/absolute/restricted/path/<database-backup>" \
  --with-public-files "/absolute/restricted/path/<public-files-backup>" \
  --with-private-files "/absolute/restricted/path/<private-files-backup>"
bench --site <training-site> list-apps
```

Do not use `--force`. Confirm that restore exited successfully and the app list
contains `frappe`, `erpnext`, `hrms`, and `apex`. Keep maintenance on while
checking that the pre-token baseline has no credential row for the training
Employee. Replace the placeholder with the Employee document name:

```bash
set -eu
TOKEN_ROW="$(bench --site <training-site> execute frappe.db.exists \
  --args '["Masar Worker Token", {"employee": "<training-worker-employee-id>"}]')"
test -z "$TOKEN_ROW"
```

Assigning the command output first preserves its exit status, so a Bench
failure stops before the empty-result test. This database check does not prove
that extra files were removed. If it fails, leave maintenance on and stop. Only
after the app and token checks pass, reopen the site in a separate gated step:

```bash
set -eu
bench --site <training-site> set-maintenance-mode off
```

Repeat the common scope checks and chosen-overlay readiness checks. If either
fails, immediately return the site to maintenance and stop:

```bash
bench --site <training-site> set-maintenance-mode on
```

Because the baseline was saved before token issuance, the successful database
restore removes the later training token row.

## Portal access

After every successful restore:

1. Open **Masar Worker Token** and select New.
2. Set **Holder Type** to **Worker**.
3. Set **Worker Type** to **Employee**.
4. Set **Worker** to **Training Worker North**, then Save.
5. Use whichever **Issue Link and QR** or **Rotate Link and QR** action is
   displayed. Either action generates a fresh link and invalidates any previous
   link. The label depends on whether the user's form can read the
   permission-level-one token field, not on lifecycle state.

**Employee**, **Enabled**, **Expires On**, and the credential fields are
read-only. Do not construct a token, edit those fields, or change the database
to alter access. The current Desk UI does not provide a reviewed driver-link
issuance action, so driver portal practice is optional and blocked unless a
later release provides one.

Treat every issued link as a credential: share it privately, exclude it from
screenshots and evidence, and never reuse or preserve it. If it is exposed,
close the affected session, generate a fresh link with the displayed action,
and notify the site administrator or security owner through your organization's
credential-incident procedure. Confirm that the old link is rejected and the
incident is recorded without the credential. If access must end, escalate to
the site administrator for approved revocation; the form has no reviewed
Disable or Set Expiry action.

## Expected evidence

The trainer checklist should show:

- the common Company, Projects, Buildings, Cost Centers, and fictional workers;
- the authorized Draft and its writable or read-only result, filtered List
  fixtures, and role-selected workflow and permission-negative branches;
- the selected track overlay and its responsible accounts;
- separate maker and checker logins;
- successful checks for each applicable Building, Project, or Company scope;
- a rehearsed native backup and restore with exact archive paths; and
- no personal link or active session token recorded in the evidence.

## Readiness assessment

The common baseline and each selected track overlay have separate gates.

Common readiness items one and two apply to Desk learners. Portal-only Drivers
use the worker or optional driver check in item four instead.

1. A Desk learner opens the authorized fixture from the role's workspace or
   exact Awesome Bar entry in the curriculum role map. A scoped learner is
   denied the opposite scope; an unscoped learner receives the rehearsed
   permission denial for the selected operation.
2. For a role that owns a workflow transition, the real Workflow Action appears
   in Action Inbox and disappears after completion. For a role with no owned
   transition, the learner names the documented next role and Action Inbox has
   no item for that source.
3. The backup and restore rehearsal succeeds, the four required apps remain
   installed, and the pre-link token record is absent.
4. A fresh worker link resolves only to the fictional Employee when worker
   portal practice is selected.

Track readiness:

- **Housing:** the request, cleaning, and custody checkpoints open for their
  intended roles. The Maintenance Technician can update the designated fields
  on the System Manager-prepared draft Work Order but cannot submit or cancel
  it.
- **Safety:** the due Safety Task Catalog item, draft round, and execution are
  visible, and the separate preparer and submitting accounts see only their
  documented actions.
- **Fleet:** Project scope holds across the route and trip fixtures, the Fuel
  Platform is selectable, and the prepared rental period has generated accrual
  rows for the rented vehicle.
- **Telecom:** the operating account sees the training contract and two SIMs
  within Company scope, while the finance account remains separate.
- **IT:** worker-link issuance is available through Desk, the settings exercise
  can be restored, and driver access remains unavailable unless a later
  release supplies reviewed Desk issuance.

The site is ready only for tracks whose common and overlay checks both pass.
After a readiness exercise changes data, restore the baseline again and issue a
new worker link if needed.

## Troubleshooting

- Missing records: inspect the relevant User Permission before changing roles.
- Missing action: check document state, workflow ownership, and the current
  permission reference.
- Wrong portal identity: close the session, generate a fresh link for the
  intended Employee, and notify the site administrator or security owner
  through your organization's credential-incident procedure. Confirm that the
  old link is rejected and the incident is recorded without the credential.
- Reset blocked by dependencies: cancel submitted training records in reverse
  order through their native lifecycle; never edit `docstatus` or generated
  ledgers.
- Unexpected email or integration traffic: stop training and isolate the site
  before continuing.

## Reset after each cohort

Close every private browser session, enter maintenance, and preserve evidence
without credentials. Remove cohort attachments through their owning documents
and native File lifecycle, then restore the pre-token baseline. Keep
maintenance on through the app-list and token-row checks above. Reopen the site
only after both checks pass, then repeat the selected role and scope checks.
The form has no reviewed Disable or Set Expiry action. Escalate to the site
administrator for approved revocation when access must end.

Issue a new worker link only after the restored baseline passes. Recreate the
disposable site when file hygiene cannot be proven, because native file restore
does not remove extra files. Never reset a site during another cohort.

## References

- [Training curriculum](README.md)
- [Permissions and role scope](../reference/permissions.md)
- [Routes and workspaces](../reference/routes-workspaces.md)
- [Troubleshooting](../reference/troubleshooting.md)
- [Records and workflows](lessons/records-and-workflows.md)
