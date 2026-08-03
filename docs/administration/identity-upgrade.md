# Upgrade Runbook: App Identity `apex_habitat` to `apex`

The Python package that ships this application was renamed from `apex_habitat`
to `apex`. A site installed **before** that rename stores the old name in four
places, and none of them are updated by pulling new code. This runbook is the
supported path for carrying such a site onto the current release.

## Status: runnable

Two things used to stop this procedure. Both are answered in place, and the answer to each
is a command you run rather than a fix you wait for.

| Was blocking | Why it happened | What you run instead |
| --- | --- | --- |
| **B1 — the repair commands are refused on the site that needs them.** `bench execute apex....` is rejected before it runs, because the site does not yet list `apex` among its installed apps — the exact condition these commands exist to repair. `AppNotInstalledError: App apex is not installed`, then `NameError: name 'apex' is not defined`, exit `1`. | `frappe.get_attr` refuses a dotted path whose leading name is missing from the site's installed apps. While the registry still names the dead package it is worse: `frappe.init` itself raises `ModuleNotFoundError: No module named 'apex_habitat'` from `setup_module_map`, so the command never starts. | The bench's own interpreter, importing the module directly. Section 4 needs no site at all, and Sections 5 and 6 import after `frappe.connect()`. Same code, without the gate. |
| **B2 — repairing the registry file has no effect until the cache is dropped.** `sites/apps.txt` is cached in Redis, so rewriting it changed nothing for the next process, and `bench --site <site> clear-cache` could not help: clearing loads every installed app's hooks and dies on the dead one before it clears anything. | `get_installed_apps(_ensure_on_bench=True)` memoises the file under `all_apps`. | A direct Redis delete of the app-discovery keys for that one site, in Section 4. It touches no other site and loads no hooks. |

| Section | Runnable today |
| --- | --- |
| 1 — Does this apply? | Yes. Reads two values, changes nothing. |
| 2 — What breaks, and why | Reference only. |
| 3 — Before you start | Yes. Ordinary backup. |
| 4 — Repair the bench registry | Yes. Preview needs no site; the cache drop follows it. |
| 5 — Repair the database identity | Yes, through the bench interpreter. |
| 6 — Migrate and verify | Yes, once Section 5 has run. |
| 7 — Rollback | Yes. Unaffected. |
| 8 — When to stop | Reference only. |
| 9 — Rehearse before the window | Yes, on a disposable bench. |

A site **already running `apex`** is unaffected by all of this and needs nothing
from this page. Section 1 tells you which case you are in.

Perform it in a planned maintenance window. It is not an emergency procedure.

Source line references below were read against Frappe `15.109.0`.

---

## 1. Does this apply to my site?

Run this on the bench, from the `frappe-bench` directory. It reads files only —
no database, no bench command, safe at any time:

```bash
grep -n 'apex' sites/apps.txt || true
```

| Output | Meaning |
| --- | --- |
| a line reading `apex` | Already canonical. **Stop — this runbook does not apply.** |
| a line reading `apex_habitat` | Pre-rename site. Continue with this runbook. |
| both, or neither | Ambiguous. Do not proceed; escalate (see [Section 8](#8-when-to-stop)). |

`|| true` is not decoration: `grep` exits non-zero when it matches nothing, and
the "neither" row is a real outcome you are meant to read rather than an error
that should abort a script running under `set -e`.

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

- **`bench migrate` fails outright — in its own set-up phase, before it reaches
  a single patch or hook.** Set-up clears the global cache, which rebuilds the
  map of every app on the bench, which means importing each one. You see
  `Could not find app "apex_habitat":` and an `ImportError`, and migrate stops
  there. (`Migrate.setUp` calls `clear_global_cache` at `frappe/migrate.py:83`,
  which rebuilds the module map at `frappe/cache_manager.py:111`;
  `frappe._load_app_hooks` re-raises at `frappe/__init__.py:1592-1601`. Migrate
  never reaches `pre_schema_updates`.)
- **The site stops serving.** Ordinary hook loading uses
  `get_installed_apps(_ensure_on_bench=True)`, which keeps only apps also listed
  in `sites/apps.txt` (`frappe/__init__.py:1561-1563`). While that file still
  says `apex_habitat`, the dead name survives the filter and raises the same
  `ImportError`. **Repairing `sites/apps.txt` is what brings the site back up**,
  and it is the first corrective step for that reason — but that read is cached
  in Redis under `all_apps` (`frappe/__init__.py:1562`), so the edited file is
  not seen until the cached value is dropped. Section 4 drops it.
- **`bench execute` cannot carry the repair.** `frappe.get_attr` rejects any
  dotted path whose leading name is missing from the site's installed apps
  (`frappe/__init__.py:1742-1746`). On a pre-rename site `apex` is exactly such
  a name, so every `bench execute apex....` raises `AppNotInstalledError` —
  including the one command meant to run first. Sections 4 and 5 import the
  module through the bench's interpreter instead, which runs the same code
  without that gate.
- **Bench commands still run, noisily.** `get_app_commands` catches the
  `ModuleNotFoundError`, prints a traceback and returns no commands
  (`frappe/utils/bench_helper.py:72-84`). Expect an alarming traceback on every
  `bench` invocation until Section 4 is done. It is not fatal.
- **A patch cannot fix this.** Patch discovery iterates the same list:
  `get_all_patches` walks `frappe.get_installed_apps()` and resolves
  `frappe.get_app_path(app, "patches.txt")`
  (`frappe/modules/patch_handler.py:89-102`). A pre-rename site never opens
  `apex/patches.txt`, so no entry in it can ever run there. The repair must come
  from outside the migrate path. That is why this is a runbook.

Because the site is down between Section 3 and Section 4, treat Sections 3
through 7 as one uninterrupted window — which, while the status above stands,
you cannot finish.

---

## 3. Before you start

```bash
bench --site <site> set-maintenance-mode on
bench --site <site> backup --with-files
```

Expected: the backup command prints `Backup Summary for <site>` followed by the
absolute paths of the SQL dump and the files archives. **Record those paths** —
Section 7 rolls back to them.

Note the current identity and version so you can confirm the upgrade landed:

```bash
bench --site <site> list-apps
```

Expected on a pre-rename site, before the source is upgraded: a row naming
`apex_habitat` and its version, alongside `frappe`, `erpnext` and `hrms`.
Record it.

Do not use `frappe.get_installed_app_version` here or anywhere else: no such
function exists, and calling it fails with
`AttributeError: module 'frappe' has no attribute 'get_installed_app_version'`
even on a perfectly healthy site. `frappe.utils.get_app_version` does exist, but
it swallows every failure and returns `"0.0.1"`
(`frappe/utils/__init__.py:1220-1224`) — a confirmation that cannot fail is not
a confirmation. `list-apps` reports the identity the site actually recorded.

---

## 4. Repair the bench registry (do this first)

`sites/apps.txt` is a **bench-level** file shared by every site on the bench.
Nothing in the application writes it — one site's upgrade must never re-point
the registry out from under its neighbours. Edit it yourself.

First upgrade the application source to the current release by your normal
deployment method, then:

```bash
cd sites
../env/bin/python -c "from apex.patches.v2_0.app_identity_cutover import rewrite_registry; \
print(rewrite_registry(open('apps.txt', encoding='utf-8').read()), end='')"
```

**Do not reach for `bench execute` here.** It cannot start on a site whose
registry still names the dead package: `frappe.init` builds the module map for
every app in `sites/apps.txt` and raises `ModuleNotFoundError: No module named
'apex_habitat'` before the command runs. The line above avoids frappe
altogether — `rewrite_registry` reads the file and returns text, so it needs no
site, no database and no hooks. It exits `0` and prints the corrected registry.

Write what it printed, or make the same edit by hand — Section 1 has already
proved the file is unambiguous: **replace the single line reading
`apex_habitat` with `apex`, and change nothing else** — not the other lines, not
their order, not the line endings, not a trailing newline. The result looks like:

```
frappe
erpnext
hrms
apex
```

If Section 1 showed anything other than exactly one `apex_habitat` line and no
`apex` line, stop and go to [Section 8](#8-when-to-stop). Which line is
authoritative is a judgement call, and guessing can detach a healthy sibling
site on the same bench. `rewrite_registry` raises `IdentityCutoverError` naming
the state it found rather than guessing which line to change.

Confirm the result:

```bash
grep -c '^apex$' sites/apps.txt || true
grep -c '^apex_habitat$' sites/apps.txt || true
```

Expected: `1` then `0`. Keep the `|| true`: the second check reports its
**expected** result by printing `0` and exiting `1`, so without it an operator
running under `set -e` aborts at the moment the step succeeds.

**Then drop the cached copy.** The edited file is not read again until the
`all_apps` entry cached in Redis is invalidated, and until you do, every command
still fails with `Could not find app "apex_habitat":` as though you had never
touched the file. `bench --site <site> clear-cache` cannot do it: that command
loads every installed app's hooks (`frappe/__init__.py:993`), and one of them is
the package that no longer exists, so the clear itself fails.

Delete the app-discovery keys for that one site instead. They are namespaced by
its database name, so no other site on the bench is touched:

```bash
cd sites
../env/bin/python - <<'PY'
import json

import redis

SITE = "<site>"
KEYS = ("all_apps", "app_hooks", "installed_apps", "app_modules",
        "installed_app_modules", "module_app", "module_installed_app")

common = json.load(open("common_site_config.json", encoding="utf-8"))
config = json.load(open(f"{SITE}/site_config.json", encoding="utf-8"))
client = redis.from_url(config.get("redis_cache") or common["redis_cache"])
print("dropped:", [k for k in KEYS if client.delete(f'{config["db_name"]}|{k}'.encode())])
PY
```

Confirm the registry is genuinely in effect:

```bash
bench --site <site> list-apps
```

It prints a row naming `apex` where the same command failed a moment earlier.
The application's own features stay unavailable until Section 5 completes,
because the database still records the old identity. That is expected.

---

## 5. Repair the database identity

Both commands here run through the bench's interpreter, not `bench execute`.
`bench execute` resolves a dotted path with `frappe.get_attr`, which refuses any
path whose leading name is missing from the site's installed apps — and the
database still says `apex_habitat`, which is the thing being repaired. It fails
with `AppNotInstalledError: App apex is not installed` and then `NameError: name
'apex' is not defined`, exit `1`. Importing the module after `frappe.connect()`
runs the same code without that gate, and commits explicitly.

Confirm what remains:

```bash
cd sites
../env/bin/python - <<'PY'
import json

import frappe

frappe.init(site="<site>")
frappe.connect()
from apex.patches.v2_0.app_identity_cutover import diagnose

print(json.dumps(diagnose(), indent=1, default=str))
PY
```

Expected output is a JSON object. On a pre-rename site, with the registry now
fixed:

```json
{
  "registry_path": "/home/frappe/frappe-bench/sites/apps.txt",
  "registry_state": "canonical",
  "installed_apps": ["frappe", "erpnext", "hrms", "apex_habitat"],
  "installed_apps_legacy": true,
  "module_def_rows": 4,
  "installed_application_rows": 1,
  "legacy_method_rows": 36,
  "sweepable_columns": 13125
}
```

`module_def_rows` is the number of modules the app ships. `sweepable_columns` is
how many text columns the sweep will inspect; it is a scan size, not a defect
count. If `registry_state` is not `canonical`, Section 4 is incomplete — the
command reports `next_step` and stops without touching the database.

Now apply the repair:

```bash
cd sites
../env/bin/python - <<'PY'
import json

import frappe

frappe.init(site="<site>")
frappe.connect()
from apex.patches.v2_0.app_identity_cutover import cutover

result = cutover()
frappe.db.commit()
print(json.dumps(result, indent=1, default=str))
PY
```

`cutover` refuses to run unless the registry is already canonical. It rewrites
the `installed_apps` global, `Module Def.app_name`, `Installed
Application.app_name`, and every stored dotted `apex_habitat.` path. It counts
each column before writing, so tables with nothing to change are never locked.
The explicit `frappe.db.commit()` is what makes the repair durable — an
interpreter session does not commit for you.

Expected output — a JSON object; the `rows` figures are site-specific:

```json
{
  "installed_apps": 1,
  "module_def": 4,
  "installed_application": 1,
  "dotted_paths": [
    {"table": "tabScheduled Job Type", "column": "method", "rows": 36}
  ]
}
```

`"installed_apps": 1` means the list was rewritten; `0` means it was already
correct. The command is idempotent — running it twice returns all-zero counts
and an empty `dotted_paths`.

---

## 6. Migrate and verify

This section depends on Section 5 having committed. Read the patch-history
warning below before you start it: it changes how long the window has to be.

```bash
bench --site <site> migrate
```

Expected: migrate now runs to completion. It must **not** print
`Could not find app "apex_habitat"`. If it does, Section 5 did not commit —
re-run `diagnose` before going further.

**Budget for a full patch replay, not a routine migrate.** Frappe decides which
patches to run by matching each entry of `apex/patches.txt` against the patch
names already recorded on the site (`frappe/modules/patch_handler.py:56,74-76`),
and those recorded names still begin `apex_habitat.` — the cutover skips the
patch-history table on purpose, because rewriting an applied-patch record would
falsify it. No name matches, so **every patch the application has ever shipped
re-runs from the beginning**. Expect migrate to print each patch name in turn
and to take far longer than an ordinary upgrade. The patches are written to be
idempotent, but this is the single longest part of the window and it must be
planned for, not discovered.

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

`clear-cache` works here, unlike in Section 4: by this point no installed app
names a package that is missing from disk.

Final confirmation — the desk loads, and:

```bash
bench --site <site> list-apps
```

Expected: a row naming `apex` and the current application version, and no row
naming `apex_habitat`. Compare it with the row you recorded in Section 3.

---

## 7. Rollback

Every step before `bench migrate` is reversible by reverting two things:

1. Restore `sites/apps.txt` to its previous contents.
2. Restore the database from the Section 3 backup:

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
  same name twice. Which line is authoritative is a judgement call, and guessing
  can detach a healthy sibling site on the same bench. `rewrite_registry` raises
  `IdentityCutoverError` here on purpose.
- The edited `sites/apps.txt` has visibly taken effect for some processes and
  not others. The cache drop in Section 4 was incomplete, and continuing past it
  writes to a database the site is still reading through a stale registry.
- `diagnose` reports `installed_apps_legacy: true` **after** a successful
  `cutover` run.
- `bench migrate` still reports `Could not find app "apex_habitat"` after
  Section 5.
- The bench hosts other sites that are **not** being upgraded in this window.
  `sites/apps.txt` is shared: once it names `apex`, every site on that bench
  whose `installed_apps` still names `apex_habitat` loses the app until it is
  cut over too. Plan them into the same window.

---

## 9. Rehearse before the window

Rehearse on a disposable bench, never on the site you intend to repair. The rehearsal
needs a genuinely pre-rename starting state: a site whose `sites/apps.txt` names
`apex_habitat` and whose `installed_apps` global lists it. That source tree is not in this
repository — its first commit already carries the canonical package — so recover it from a
deployment artifact of that era, or reproduce the state by writing the four stored values
this runbook repairs.

```bash
bench new-site rehearsal.localhost
bench --site rehearsal.localhost install-app erpnext hrms
bench --site rehearsal.localhost install-app apex_habitat
bench --site rehearsal.localhost migrate
```

Seed one legacy dotted path so the sweep has something real to find and you can prove it
was rewritten rather than merely not crashing:

```bash
bench --site rehearsal.localhost mariadb -e \
  "UPDATE \`tabNumber Card\` SET method='apex_habitat.habitat.api.dashboard.probe' LIMIT 1"
```

Then run Sections 3 through 6 verbatim against that site.

**What proves it worked.** All twelve must hold.

1. Before Section 4, `bench --site rehearsal.localhost migrate` fails with
   `Could not find app "apex_habitat"` — the rehearsal really started from the broken
   state.
2. `rewrite_registry` prints the corrected registry text on that still-broken site, with
   no `AppNotInstalledError`.
3. After the registry is written and the cache keys are dropped, `list-apps` prints
   `apex` where the same command failed a moment earlier.
4. Between Sections 4 and 5, `diagnose` returns `registry_state` `canonical` and no
   `next_step` key.
5. Section 5's `cutover` returns `installed_apps: 1` and a `dotted_paths` entry for
   `tabNumber Card` / `method` with `rows` at least 1.
6. Re-running `cutover` immediately returns all zeros and an empty `dotted_paths`, which
   is idempotence after a real write.
7. Section 6's `bench migrate` completes with no `apex_habitat` message. Record how long
   it takes and how many patches it replays — that figure is the maintenance window a real
   site needs.
8. The seeded Number Card `method` now reads `apex.habitat.api.dashboard.probe`.
9. `SELECT defvalue FROM tabDefaultValue WHERE defkey='installed_apps'` contains `"apex"`
   exactly once and `"apex_habitat"` zero times.
10. The patch-history table still contains its historical `apex_habitat.*` patch names.
    The sweep skips audit tables on purpose — rewriting applied-patch history would
    falsify the migration record — and that is also why Section 6 replays patches.
11. Every command in Sections 1 through 6 exits `0` on its expected result, so the
    sequence survives `set -e`.
12. The desk loads and an application workspace opens.

**Count with `LOCATE`, not `LIKE`.** In SQL `LIKE`, `_` matches any single character, so
`WHERE method LIKE 'apex_habitat%'` also matches every canonical `apex.habitat....` path
and reports a repaired site as still broken. Use
`WHERE LOCATE('apex_habitat.', method) > 0`, which is what the sweep itself uses.

**What a rehearsal on written values cannot show.** If you reproduce the starting state by
writing the four stored identities rather than installing the old package, anything that
would differ because that package was installed — a table only it created, a fixture only
it shipped — is outside what the rehearsal covers. The four stored places are what this
runbook repairs, and those are genuinely exercised.
