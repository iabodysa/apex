# Installation

This guide installs a pinned Apex revision on a Frappe site and verifies the
result. Prove the exact revision in staging before production.

## Supported stack

| Component | Supported line |
|---|---|
| Frappe Framework | Version 15 |
| ERPNext | Version 15 |
| HRMS | Version 15 |
| Python | `>=3.10,<3.15` |
| Node.js | 20 for portal development and bundle verification |

Apex declares Frappe, ERPNext, and HRMS as required apps. Install all three on
the target site before Apex. Use one reviewed Version 15 combination across the
bench and prove it in staging.

## Prerequisites

Prepare a working Frappe Bench with its database, Redis services, workers, and
an existing target site. Provision Frappe, ERPNext, and HRMS from a reviewed
bench artifact or immutable tags and full commit SHAs before the production
maintenance window. Do not fetch a moving Version 15 branch during deployment.

From the bench directory, inspect the staged combination:

```bash
bench version
bench --site <site> list-apps
git -C apps/frappe rev-parse HEAD
git -C apps/erpnext rev-parse HEAD
git -C apps/hrms rev-parse HEAD
```

The site must already list `frappe`, `erpnext`, and `hrms` at the reviewed
combination. Stop if an app is missing or any source revision differs.

### Existing production site

Schedule a maintenance window. Replace the backup directory with an existing
absolute directory restricted to deployment administrators, then enter
maintenance before taking the backup:

```bash
set -eu
umask 077
test -d /absolute/restricted/backup-directory
test -w /absolute/restricted/backup-directory
bench --site <site> set-maintenance-mode on
bench --site <site> backup --with-files \
  --backup-path /absolute/restricted/backup-directory
```

Read the successful backup summary. Replace these placeholders with its exact
absolute output paths and verify every file before changing the bench:

```bash
set -eu
test -f "/absolute/restricted/backup-directory/<database-backup>"
test -f "/absolute/restricted/backup-directory/<public-files-backup>"
test -f "/absolute/restricted/backup-directory/<private-files-backup>"
test -f "/absolute/restricted/backup-directory/<site-config-backup>"
```

If backup or verification fails, stop with maintenance enabled.

## Install Apex

This sequence is for a new checkout. Stop if `apps/apex` already exists,
including as a symlink; an existing checkout needs its own reviewed update
procedure.

Replace both revision placeholders with approved immutable values. Git verifies
the tag's peeled commit before any dependency, build, reload, or site command:

```bash
set -eu

APEX_TAG='<reviewed-release-tag>'
APEX_COMMIT='<reviewed-full-commit-sha>'

test ! -e apps/apex
test ! -L apps/apex
git clone --no-checkout --branch "$APEX_TAG" --single-branch \
  https://github.com/iabodysa/apex.git apps/apex
test "$(git -C apps/apex rev-parse "refs/tags/${APEX_TAG}^{commit}")" = "$APEX_COMMIT"
git -C apps/apex checkout --detach "$APEX_COMMIT"
test "$(git -C apps/apex rev-parse HEAD)" = "$APEX_COMMIT"

bench setup requirements apex
bench build --app apex
bench --site <site> install-app apex
bench --site <site> migrate
```

Any failed check stops the sequence. Do not continue from a partial checkout.

Installation provisions Apex roles, role profiles, settings, workflows, seed
records, and navigation. Migration reapplies the idempotent provisioning needed
by an upgraded site.

## Complete first-run setup

When Apex is installed before the native setup wizard is completed on a fresh
site, the wizard adds three Apex configuration steps. Choose:

- Default Company for Habitat and Salis.
- Default Cost Center for Salis fleet postings.
- General Ledger posting, off by default.
- Payment routing: keep `Payment Entry` as the only target for this release and
  keep target auto-submit off.
- Email notifications, off until outgoing email is configured.
- Operational notifications, off by default.
- Driver portal, off by default.
- Fleet approval routing, on by default.
- Housing and custody-damage salary deductions, both off by default.

Leave an unknown Company or Cost Center blank and configure it later in
`Habitat Settings` or `Salis Settings`. Keep General Ledger posting and salary
deductions off until Finance, HR, accounts, salary components, and the
authorizer are configured. Missing deduction prerequisites cause the setup
logic to leave deduction rules disabled.

The wizard selects only the payment target DocType; it does not create the
required field map. That choice alone is not production-ready. Do not select
`Payment Order` or a custom target, and do not use **Create Payment** until
Finance has reviewed and validated a complete `Payment Entry` field map on the
target site.

If the native setup wizard was already completed, review the same choices in
`Apex Settings`, `Habitat Settings`, `Salis Settings`,
`Payment Routing Settings`, and `Salary Deduction Policy`.

## Verify the installation

Run:

```bash
bench --site <site> list-apps
bench --site <site> scheduler status
bench doctor --site <site>
```

Expected results:

- `frappe`, `erpnext`, `hrms`, and `apex` appear in the installed-app list.
- Installation and migration finish without a traceback or failed patch.
- Scheduler and workers are healthy.
- A System Manager can open an authorized Apex workspace.
- The five Single settings records reflect the reviewed setup choices.
- General Ledger posting and salary deductions remain off unless explicitly
  configured.

For an existing production site, end maintenance only after these checks pass:

```bash
bench --site <site> set-maintenance-mode off
```

## Local development

Run backend tests only on a disposable test site:

```bash
bench --site <test-site> run-tests --app apex
```

Run the current frontend unit checks and build all six portal packages from
`frontend/`:

```bash
npm ci
npm test
npm run build
```

Then refresh Frappe assets from the bench directory:

```bash
bench build --app apex
```

`npm test` covers the shared tests plus the worker phone and QR-color checks; it
is not a test suite for every portal. `npm run build` builds all six portal
packages. Tests and guards must exit successfully. A portal rebuild should
update only the expected compiled assets.

## Safe stop conditions

Stop and preserve logs when an install, migration, build, worker check, or test
fails. Do not bypass a failed patch, edit the database directly, use force
flags, or repeatedly retry a state-changing command without identifying the
cause. Keep maintenance mode enabled on an existing production site until the
failure is reviewed and a recovery decision is made.
