# Prepare and Reset Apex Training

Use this procedure only on a disposable, non-production site. It creates a repeatable Apex
operation with fictional people, locations, vehicles, assets, contracts, and evidence.

## Result

Before each cohort, the trainer can restore one clean baseline, select the required product
journey, prove role scope, and issue a fresh worker link without retaining credentials from
the previous cohort.

## Isolate the site

- Disable outbound email, webhooks, payment connections, and production integrations.
- Use a dedicated training administrator for setup, backup, and reset.
- Store backups in an encrypted directory restricted to training administrators.
- Use fictional identifiers, phone numbers, plates, documents, signatures, and attachments.
- Keep maker, reviewer, finance, trainer, and learner accounts separate.

Never clone production data into the training site.

## Build the shared operating context

Create:

- **Apex Training Company** with abbreviation **ATC**;
- **Training North** and **Training South** Projects and Cost Centers;
- **Training Campus** with **Training Residence North** and **Training Residence South**;
- one Room with two Beds in each Building; and
- fictional Employees for a resident, worker, driver, supervisor, reviewer, and finance user.

For each learner role, prepare one item inside its assigned Building, Project, or Company and
one item outside that scope. Prepare a real task or workflow handoff only through its source
record; do not insert inbox or workflow rows directly.

The shared baseline must contain no **Masar Worker Token**. Take the baseline backup before
issuing any personal link.

## Add only the journeys being taught

### Housing

- a resident arrival, available bed, assignment, transfer option, and checkout path;
- a Resident Request and Maintenance Request;
- a safe draft Maintenance Work Order;
- a Cleaning Log checkpoint;
- a Custody Article with sufficient fictional stock; and
- one Utility Account per training Building.

### Safety

- an active Safety Task Catalog item for the selected Building and cadence;
- a due round; and
- a finding that requires evidence and a separate follow-up role.

### Fleet

- two fictional driver Employees and active Salis Driver records;
- one active owned vehicle and assignment;
- a Transport Request, Route Plan, and Dispatch Trip;
- a Fuel Platform and a fuel scenario; and
- one rented vehicle, Supplier, Rental Office, and normally generated accrual period.

### Telecom

- a fictional Supplier and non-stock service Item;
- a Telecom Contract with a safe near-term review date;
- three fictional SIM Cards in different operating states; and
- one custody assignment and one transfer scenario.

Leave real ICCIDs, numbers, invoices, payment records, and purchase records out of the
baseline.

### IT

- one Employee eligible for worker access;
- the current portal appearance settings recorded before the exercise; and
- one expected-access and one expected-denial case for each supported persona.

## Apply role scope

- Resident Supervisors receive only their training Building.
- Fleet Project Managers and Fleet Supervisors receive only their training Project.
- SIM Operations Users receive only **Apex Training Company**.
- Makers and reviewers use separate accounts.
- Finance reviewers receive only the finance step required by the selected journey.

Test every scoped account. A North Building, Project, or Company account must not find or
open its South counterpart. Verify oversight accounts against their intentionally broader
role instead of treating that access as a scope failure. Never add a broader role to hide an
unexpected result.

## Save and rehearse the baseline

Replace the directory below with an existing restricted absolute path. Enter maintenance,
take the backup, and read the successful backup summary:

```bash
set -eu
umask 077
test -d /absolute/restricted/path
test -w /absolute/restricted/path
bench --site <training-site> set-maintenance-mode on
bench --site <training-site> backup --with-files \
  --backup-path /absolute/restricted/path
```

Record and verify the exact paths printed by Bench:

```bash
set -eu
test -f "/absolute/restricted/path/<database-backup>"
test -f "/absolute/restricted/path/<public-files-backup>"
test -f "/absolute/restricted/path/<private-files-backup>"
test -f "/absolute/restricted/path/<site-config-backup>"
```

Rehearse the restore before training:

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

Do not use `--force`. Confirm that `frappe`, `erpnext`, `hrms`, and `apex` remain installed.
If that check succeeds, reopen the training site:

```bash
bench --site <training-site> set-maintenance-mode off
```

Do not open Desk or issue, rotate, or test a personal token while maintenance mode is on.

Native file restore overlays the file trees; it does not remove unexpected extra files. If
cohort files cannot be fully accounted for, recreate the disposable site or restore an
infrastructure snapshot that replaces the database and both file trees.

## Issue worker access after restore

1. Open **Masar Worker Token** and create a record.
2. Set **Holder Type** to **Worker**, **Worker Type** to **Employee**, and select the fictional
   training Employee.
3. Save, then use the displayed **Issue Link and QR** or **Rotate Link and QR** action.
4. Open the link only in the learner's private browser session.
5. Confirm that it resolves to the intended fictional Employee and no other identity.

The link is a credential. Never preserve it in screenshots, chat, tickets, exports, or
training evidence. Rotate it immediately after exposure.

Do not construct driver or worker URLs by hand, edit credential fields, or alter the database
to create access. If the current Desk does not offer a reviewed issuance action for the
required holder, omit that portal exercise.

## Readiness check

The site is ready when:

- each learner opens only the intended Building, Project, or Company records;
- each maker and reviewer sees only the action owned by that role;
- every selected journey has a realistic source, action, evidence, and handoff;
- the backup and restore rehearsal completes without errors;
- the four required apps remain installed; and
- a newly issued worker link resolves only to the selected fictional Employee.

Record results without credentials or personal data.

## Reset after each cohort

1. Close every learner browser session, but keep the trainer's administrative session open.
2. While Desk is still available, open each cohort-created record and remove its attachments
   through the record's attachment controls. Check the **File** list for each removed filename.
   If the cohort files cannot be fully accounted for, stop and recreate the disposable site
   or restore a replacing infrastructure snapshot.
3. Enter maintenance mode and restore the pre-token baseline. Keep maintenance mode on
   through the restore and app check:

```bash
set -eu
bench --site <training-site> set-maintenance-mode on
bench --site <training-site> restore \
  "/absolute/restricted/path/<database-backup>" \
  --with-public-files "/absolute/restricted/path/<public-files-backup>" \
  --with-private-files "/absolute/restricted/path/<private-files-backup>"
bench --site <training-site> list-apps
```

4. Confirm that `frappe`, `erpnext`, `hrms`, and `apex` still appear, then reopen the site:

```bash
bench --site <training-site> set-maintenance-mode off
```

5. Only after maintenance mode is off, confirm that no token row remains for the training
   Employee:

```bash
set -eu
TOKEN_ROW="$(bench --site <training-site> execute frappe.db.exists \
  --args '["Masar Worker Token", {"employee": "<training-worker-employee-id>"}]')"
test -z "$TOKEN_ROW"
```

6. Repeat the role-scope checks for the next selected journey in Desk. Issue a fresh worker
   link only if that cohort includes a portal exercise.

If any post-restore check fails, immediately turn maintenance mode on again and do not admit
learners. Never reset a site while another cohort is using it.

## Related guides

- [Training home](README.md)
- [Follow Work from Request to Proof](foundations.md)
- [Worker and Driver Portals](portals-masar-driver.md)
- [Troubleshooting](../reference/troubleshooting.md)
