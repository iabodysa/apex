# Legacy App Identity Upgrade

Use this runbook only for a site installed under the former application name
`apex_habitat`. A site already registered as `apex` does not need this
procedure.

The bench registry is shared by every site on the bench. Upgrade all affected
sites in one planned window, or move them to separate benches first.

## Confirm the starting state

From the bench directory:

```bash
grep -nE '^(apex|apex_habitat)$' sites/apps.txt
```

- One `apex` line means the bench registry is already canonical.
- One `apex_habitat` line means this runbook applies.
- Both, neither, or duplicate lines are ambiguous. Stop and investigate.

Confirm the site database still names the former app:

```bash
bench --site <site> mariadb \
  -e "SELECT defvalue FROM tabDefaultValue WHERE defkey='installed_apps'"
```

Do not continue unless the registry and database state are understood for every
site on the bench.

## Prepare

Enter a maintenance window and create a file-inclusive backup:

```bash
bench --site <site> set-maintenance-mode on
bench --site <site> backup --with-files
```

Record the SQL, public-files, and private-files paths printed by the backup.
Deploy the current Apex source through the normal release process, but do not
run `bench migrate` yet.

## Repair the bench registry first

Preview the exact registry change:

```bash
bench --site <site> execute \
  apex.patches.v2_0.app_identity_cutover.preview_registry
```

Review the output. Manually replace the single `apex_habitat` line in
`sites/apps.txt` with `apex`; preserve every other line.

Verify the result:

```bash
grep -c '^apex$' sites/apps.txt
grep -c '^apex_habitat$' sites/apps.txt
```

Expected counts are `1` and `0`. Do not run the database cutover while the
registry is legacy or ambiguous.

## Repair the site database

Inspect remaining legacy references:

```bash
bench --site <site> execute \
  apex.patches.v2_0.app_identity_cutover.diagnose
```

The result must report `"registry_state": "canonical"` before the next command.
Apply the idempotent cutover:

```bash
bench --site <site> execute \
  apex.patches.v2_0.app_identity_cutover.cutover
```

The command updates the installed-app global, app-name records, and stored
dotted Python paths. It deliberately does not rewrite append-only audit
history.

Run `cutover` a second time. An already-clean site returns zero changes and no
dotted-path rewrites.

## Migrate and verify

```bash
bench --site <site> migrate
bench build --app apex
bench --site <site> clear-cache
```

Run the diagnostic again:

```bash
bench --site <site> execute \
  apex.patches.v2_0.app_identity_cutover.diagnose
```

Verify all of the following:

- `registry_state` is `canonical`.
- `installed_apps` contains `apex` and not `apex_habitat`.
- `installed_apps_legacy` is `false`.
- `module_def_rows`, `installed_application_rows`, and
  `legacy_method_rows` are zero.
- Migration did not report `Could not find app "apex_habitat"`.
- Desk opens and an Apex workspace loads.

Restore normal service only after these checks:

```bash
bench --site <site> set-maintenance-mode off
```

## Stop conditions

Stop instead of improvising when:

- `sites/apps.txt` is missing, duplicated, or names both identities;
- another site on the same bench cannot be upgraded in the same window;
- `diagnose` still reports legacy rows after `cutover`;
- migration still reports the former package; or
- the backup paths cannot be confirmed.

## Rollback

Keep the previous application source and backup until verification completes.
If rollback is required, restore the previous `sites/apps.txt`, deploy the
previous source, and restore the recorded backup:

```bash
bench --site <site> restore <sql-dump> \
  --with-public-files <public-files> \
  --with-private-files <private-files>
```

Rehearse the complete sequence on a disposable copy of a pre-rename site before
the first production cutover.
