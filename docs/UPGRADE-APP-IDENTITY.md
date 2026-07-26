# Upgrade Runbook: App Identity `apex_habitat` to `apex`

The Python package that ships this application was renamed from `apex_habitat`
to `apex`. A site installed **before** that rename stores the old name in four
places, and none of them are updated by pulling new code. This runbook is the
supported path for carrying such a site onto the current release.

Perform it in a planned maintenance window. It is not an emergency procedure.

---

## 1. Does this apply to my site?

Run this on the bench, from the `frappe-bench` directory. It reads files only —
no database, no bench command, safe at any time:

```bash
grep -n 'apex' sites/apps.txt
```

| Output | Meaning |
| --- | --- |
| a line reading `apex` | Already canonical. **Stop — this runbook does not apply.** |
| a line reading `apex_habitat` | Pre-rename site. Continue with this runbook. |
| both, or neither | Ambiguous. Do not proceed; escalate (see [Section 8](#8-when-to-stop)). |

Confirm the same on the database side:

```bash
bench --site <site> mariadb -e "SELECT defvalue FROM tabDefaultValue WHERE defkey='installed_apps'"
```

Expected on a pre-rename site: a JSON array whose elements include
`"apex_habitat"` — for example
`["frappe","erpnext","hrms","apex_habitat"]`.

---

## 2. What breaks, and why

The application code no longer contains an `apex_habitat` package. As soon as
the new source is on the bench, every stored `apex_habitat` reference names a
module that cannot be imported.

- **`bench migrate` fails outright.** `Migrate.pre_schema_updates` calls
  `frappe.get_hooks("before_migrate", app_name=app)` for every entry of the
  unfiltered `frappe.get_installed_apps()` (`frappe/migrate.py:113-115`).
  `frappe._load_app_hooks` prints `Could not find app "apex_habitat":` and
  re-raises the `ImportError` (`frappe/__init__.py:1592-1601`).
- **The site stops serving.** Ordinary hook loading uses
  `get_installed_apps(_ensure_on_bench=True)`, which keeps only apps also listed
  in `sites/apps.txt` (`frappe/__init__.py:1561-1563`). While that file still
  says `apex_habitat`, the dead name survives the filter and raises the same
  `ImportError`. **Repairing `sites/apps.txt` is what brings the site back up**,
  and it is the first corrective step for that reason.
- **Bench commands still run, noisily.** `get_app_commands` catches the
  `ModuleNotFoundError`, prints a traceback and returns no commands
  (`frappe/utils/bench_helper.py:72-84`). Expect an alarming traceback on every
  `bench` invocation until Step 4 is done. It is not fatal.
- **A patch cannot fix this.** Patch discovery iterates the same list:
  `get_all_patches` walks `frappe.get_installed_apps()` and resolves
  `frappe.get_app_path(app, "patches.txt")`
  (`frappe/modules/patch_handler.py:89-102`). A pre-rename site never opens
  `apex/patches.txt`, so no entry in it can ever run there. The repair must come
  from outside the migrate path. That is why this is a runbook.

Because the site is down between Step 3 and Step 4, treat Steps 3 through 7 as
one uninterrupted window.

---

## 3. Before you start

```bash
bench --site <site> set-maintenance-mode on
bench --site <site> backup --with-files
```

Expected: the backup command prints `Backup Summary for <site>` followed by the
absolute paths of the SQL dump and the files archives. **Record those paths** —
Section 7 rolls back to them.

Note the current version so you can confirm the upgrade landed:

```bash
bench --site <site> execute "frappe.get_installed_app_version" --args "['apex_habitat']"
```

---

## 4. Repair the bench registry (do this first)

`sites/apps.txt` is a **bench-level** file shared by every site on the bench.
Nothing in the application writes it — one site's upgrade must never re-point
the registry out from under its neighbours. Edit it yourself.

First upgrade the application source to the current release by your normal
deployment method, then:

```bash
bench --site <site> execute apex.patches.v2_0.app_identity_cutover.preview_registry
```

This prints the corrected file contents and touches nothing. Expected output is
your existing `apps.txt` with the single `apex_habitat` line replaced by `apex`,
every other line and line ending unchanged:

```
frappe
erpnext
hrms
apex
```

If it raises `IdentityCutoverError` instead, the registry is ambiguous — go to
[Section 8](#8-when-to-stop).

Write exactly that text to `sites/apps.txt`, then confirm:

```bash
grep -c '^apex$' sites/apps.txt
grep -c '^apex_habitat$' sites/apps.txt
```

Expected: `1` then `0`.

The site should now respond again, with the application's own features
unavailable (its hooks do not load until Step 5 completes). That is expected.

---

## 5. Repair the database identity

Confirm what remains:

```bash
bench --site <site> execute apex.patches.v2_0.app_identity_cutover.diagnose
```

Expected output is a JSON object. On a pre-rename site, with the registry now
fixed:

```json
{
  "registry_path": "/home/frappe/frappe-bench/sites/apps.txt",
  "registry_state": "canonical",
  "installed_apps": ["frappe", "erpnext", "hrms", "apex_habitat"],
  "installed_apps_legacy": true,
  "module_def_rows": 5,
  "installed_application_rows": 1,
  "legacy_method_rows": 0,
  "sweepable_columns": 2841
}
```

`module_def_rows` is the number of modules the app ships. `sweepable_columns` is
how many text columns the sweep will inspect; it is a scan size, not a defect
count. If `registry_state` is not `canonical`, Step 4 is incomplete — the
command reports `next_step` and stops without touching the database.

Now apply the repair:

```bash
bench --site <site> execute apex.patches.v2_0.app_identity_cutover.cutover
```

`cutover` refuses to run unless the registry is already canonical. It rewrites
the `installed_apps` global, `Module Def.app_name`, `Installed
Application.app_name`, and every stored dotted `apex_habitat.` path. It counts
each column before writing, so tables with nothing to change are never locked.
`bench execute` commits when the command returns
(`frappe/commands/utils.py:283-284`).

Expected output — a JSON object; the `rows` figures are site-specific:

```json
{
  "installed_apps": 1,
  "module_def": 5,
  "installed_application": 1,
  "dotted_paths": [
    {"table": "tabNumber Card", "column": "method", "rows": 6}
  ]
}
```

`"installed_apps": 1` means the list was rewritten; `0` means it was already
correct. The command is idempotent — running it twice returns all-zero counts
and an empty `dotted_paths`.

---

## 6. Migrate and verify

```bash
bench --site <site> migrate
```

Expected: migrate now runs to completion. It must **not** print
`Could not find app "apex_habitat"`. If it does, Step 5 did not commit — re-run
`diagnose` before going further.

Verify the identity is fully canonical:

```bash
bench --site <site> execute apex.patches.v2_0.app_identity_cutover.diagnose
```

Expected: `registry_state` is `canonical`, `installed_apps_legacy` is `false`,
`installed_apps` contains `"apex"` and not `"apex_habitat"`, and
`module_def_rows`, `installed_application_rows` and `legacy_method_rows` are all
`0`.

Then restore normal service:

```bash
bench --site <site> clear-cache
bench build --app apex
bench --site <site> set-maintenance-mode off
```

Final confirmation — the desk loads, and:

```bash
bench --site <site> execute "frappe.get_installed_app_version" --args "['apex']"
```

Expected: the current application version string, not an error.

---

## 7. Rollback

Every step before `bench migrate` is reversible by reverting two things:

1. Restore `sites/apps.txt` to its previous contents.
2. Restore the database from the Step 3 backup:

```bash
bench --site <site> restore <path-to-sql-dump> --with-public-files <path> --with-private-files <path>
```

Then redeploy the previous application source. Once `bench migrate` has run,
schema changes from the new release are applied and the database backup is the
only route back.

---

## 8. When to stop

Stop and escalate rather than improvise if any of these hold:

- `sites/apps.txt` lists **both** `apex` and `apex_habitat`, or neither, or the
  same name twice. `preview_registry` raises `IdentityCutoverError` here on
  purpose: which line is authoritative is a judgement call, and guessing can
  detach a healthy sibling site on the same bench.
- `diagnose` reports `installed_apps_legacy: true` **after** a successful
  `cutover` run.
- `bench migrate` still reports `Could not find app "apex_habitat"` after
  Step 5.
- The bench hosts other sites that are **not** being upgraded in this window.
  `sites/apps.txt` is shared: once it names `apex`, every site on that bench
  whose `installed_apps` still names `apex_habitat` loses the app until it is
  cut over too. Plan them into the same window.

---

## 9. Rehearsal specification

This runbook has been proven at the logic level only — the identity-rewriting
functions are unit-tested against fixtures in
`apex/patches/v2_0/test_app_identity_cutover.py`, which runs without a site. The
end-to-end sequence has **not** been rehearsed against a live bench. Do that
once, on a scratch site, before running it on a real one.

**Set-up.** On a disposable bench, create a site and install the application at
a release **before** the rename (the last version whose tree still contains an
`apex_habitat/` directory):

```bash
bench new-site rehearsal.localhost
bench --site rehearsal.localhost install-app erpnext hrms
bench --site rehearsal.localhost install-app apex_habitat
bench --site rehearsal.localhost migrate
```

Confirm the starting state is genuinely pre-rename: `sites/apps.txt` contains
`apex_habitat`, and the `installed_apps` global lists `apex_habitat`. Note that
re-installing an app over an existing site is not the same as a fresh site —
use a genuinely new site here.

**Seed a legacy dotted path** so the sweep has something real to find, and the
rehearsal can prove it was rewritten rather than merely not crashing:

```bash
bench --site rehearsal.localhost mariadb -e \
  "UPDATE \`tabNumber Card\` SET method='apex_habitat.habitat.api.dashboard.probe' LIMIT 1"
```

**Exercise.** Check out the current release, then run Sections 3 through 6
verbatim against `rehearsal.localhost`.

**Observations that prove it worked.** All of these must hold:

1. Before Step 4, `bench --site rehearsal.localhost migrate` fails with
   `Could not find app "apex_habitat"`. This confirms the rehearsal really
   started from the broken state, rather than from an already-canonical site.
2. After Step 4 and before Step 5, `diagnose` returns `registry_state`
   `canonical` and a `next_step` key is **absent**.
3. Step 5's `cutover` returns `installed_apps: 1` and a `dotted_paths` entry for
   `tabNumber Card` / `method` with `rows` at least 1.
4. Re-running `cutover` immediately returns `installed_apps: 0`,
   `module_def: 0`, `installed_application: 0` and `dotted_paths: []`, proving
   idempotence.
5. Step 6's `bench migrate` completes with no `apex_habitat` message.
6. The seeded Number Card `method` now reads
   `apex.habitat.api.dashboard.probe`.
7. `SELECT defvalue FROM tabDefaultValue WHERE defkey='installed_apps'` contains
   `"apex"` exactly once and `"apex_habitat"` zero times.
8. `tabPatch Log` still contains its historical `apex_habitat.*` patch names —
   the sweep deliberately skips audit tables, and rewriting applied-patch
   history would falsify the migration record.
9. The desk loads and an application workspace opens.

Record the observed output of each step. Any divergence is a defect in this
runbook, not an operator error.
