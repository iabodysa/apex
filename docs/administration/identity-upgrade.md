# Upgrade Runbook: App Identity `apex_habitat` to `apex`

The Python package that ships this application was renamed from `apex_habitat`
to `apex`. A site installed **before** that rename stores the old name in four
places, and none of them are updated by pulling new code. This runbook is the
supported path for carrying such a site onto the current release.

## Status: deferred — do not run Sections 4 to 6

Set **31 July 2026**, after the whole sequence was walked end to end against a
live pre-rename site. It could not be completed. Two defects stop it, and both
are repeated in place at the step where you meet them.

| Blocker | Symptom | Where it stops you |
| --- | --- | --- |
| **B1 — the repair commands are refused on the site that needs them.** A `bench execute` of any `apex....` path is rejected before it runs, because the site does not yet list `apex` among its installed apps — the exact condition these commands exist to repair. | `AppNotInstalledError: App apex is not installed`, then `NameError: name 'apex' is not defined`, exit status `1`. On a site whose cache is cold it fails earlier still, while the command is starting up. | Sections 4, 5 and 6. Worst on `preview_registry`, whose whole purpose is to run **before** the registry is repaired, so it can never run at all. |
| **B2 — repairing the registry file has no effect until the cached copy is dropped.** The contents of `sites/apps.txt` are cached in Redis. Rewriting the file changes nothing for any process that has already read it. | The site behaves as though the file were never edited, and Section 5's first write fails. `bench --site <site> clear-cache` does not help: clearing the cache loads every installed app's hooks, and one of them is the package that no longer exists, so the clear itself fails. | Section 4 (which never tells you to clear anything) into Section 5. |

There is **no safe stopping point** between Sections 4 and 6: repairing the
registry by hand leaves the site serving without the application, and Section 5
cannot then complete the repair. Do not open the maintenance window.

| Section | Runnable today |
| --- | --- |
| 1 — Does this apply? | Yes. Reads two values, changes nothing. |
| 2 — What breaks, and why | Reference only. |
| 3 — Before you start | Yes. Ordinary backup. |
| 4 — Repair the bench registry | **Blocked** (B1, B2). |
| 5 — Repair the database identity | **Blocked** (B1). |
| 6 — Migrate and verify | **Blocked** (depends on Section 5). |
| 7 — Rollback | Yes. Unaffected. |
| 8 — When to stop | Reference only. |
| 9 — Exit criteria | Reference only. |

A site **already running `apex`** is unaffected by all of this and needs nothing
from this page. Section 1 tells you which case you are in.

This runbook is kept, not withdrawn. The procedure below remains the intended
path and becomes usable again once both blockers are fixed **and** the sequence
has been rehearsed against a genuinely pre-rename site. Section 9 states what has
to be true before this status changes, including one prerequisite for that
rehearsal that neither blocker covers.

Perform it in a planned maintenance window when it is un-deferred. It is not an
emergency procedure.

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
  not seen until the cached value is dropped. That is blocker **B2**.
- **The repair commands themselves are refused.** `frappe.get_attr` rejects any
  dotted path whose leading name is missing from the site's installed apps
  (`frappe/__init__.py:1742-1746`). On a pre-rename site `apex` is exactly such
  a name, so every `bench execute apex....` below raises
  `AppNotInstalledError` — including the one command meant to run first. That is
  blocker **B1**, and it is why this runbook is deferred rather than merely
  imperfect.
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

> **Blocked — B1 and B2.** `preview_registry` cannot run on a pre-rename site,
> and the registry edit does not take effect once you make it. Read this
> section; do not execute it.

`sites/apps.txt` is a **bench-level** file shared by every site on the bench.
Nothing in the application writes it — one site's upgrade must never re-point
the registry out from under its neighbours. Edit it yourself.

First upgrade the application source to the current release by your normal
deployment method, then:

```bash
bench --site <site> execute apex.patches.v2_0.app_identity_cutover.preview_registry
```

**This is the command B1 blocks hardest.** It exists to print the corrected file
*before* the registry is repaired, which is precisely the state in which the
site refuses to run it: it exits `1` with `AppNotInstalledError: App apex is not
installed`, followed by `NameError: name 'apex' is not defined`. There is no
flag or ordering that avoids this.

The edit it would have printed is small enough to make by hand, and Section 1
has already proved the file is unambiguous: **replace the single line reading
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
site on the same bench. (When B1 is fixed, `preview_registry` raises
`IdentityCutoverError` for you in that case instead.)

Confirm the result:

```bash
grep -c '^apex$' sites/apps.txt || true
grep -c '^apex_habitat$' sites/apps.txt || true
```

Expected: `1` then `0`. Keep the `|| true`: the second check reports its
**expected** result by printing `0` and exiting `1`, so without it an operator
running under `set -e` aborts at the moment the step succeeds.

**Then the cached copy must be dropped, and this is where B2 stops you.** The
edited file is not read again until the `all_apps` entry cached in Redis is
invalidated. `bench --site <site> clear-cache` cannot do it: that command loads
every installed app's hooks (`frappe/__init__.py:993`), and one of them is the
package that no longer exists, so it fails with the same
`Could not find app "apex_habitat":`. During the rehearsal the only thing
observed to release the site was deleting the cached `all_apps` entry from Redis
directly. That is a finding, not a supported step — a supported way to drop it
is part of what Section 9 requires before this runbook is used.

Once the registry is genuinely in effect, the site responds again with the
application's own features unavailable, because its hooks do not load until
Section 5 completes. That is expected — and it is also as far as this procedure
currently gets.

---

## 5. Repair the database identity

> **Blocked — B1.** Both commands in this section are refused on a pre-rename
> site with `AppNotInstalledError: App apex is not installed`, exit `1`. The
> database identity is what makes `apex` an installed app, so neither command can
> reach the state that would let it run.

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
count. If `registry_state` is not `canonical`, Section 4 is incomplete — the
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

> **Blocked.** This section depends on Section 5 having committed, which it
> cannot. Read the patch-history warning below before it is un-deferred: it
> changes how long the window has to be.

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

- The status at the top of this page still reads **deferred**. That is itself a
  stop condition for Sections 4 to 6.
- `sites/apps.txt` lists **both** `apex` and `apex_habitat`, or neither, or the
  same name twice. Which line is authoritative is a judgement call, and guessing
  can detach a healthy sibling site on the same bench. (`preview_registry`
  raises `IdentityCutoverError` here on purpose, once it can run at all.)
- The edited `sites/apps.txt` has visibly taken effect for some processes and
  not others. That is blocker B2, and continuing past it writes to a database
  the site is still reading through a stale registry.
- `diagnose` reports `installed_apps_legacy: true` **after** a successful
  `cutover` run.
- `bench migrate` still reports `Could not find app "apex_habitat"` after
  Section 5.
- The bench hosts other sites that are **not** being upgraded in this window.
  `sites/apps.txt` is shared: once it names `apex`, every site on that bench
  whose `installed_apps` still names `apex_habitat` loses the app until it is
  cut over too. Plan them into the same window.

---

## 9. Exit criteria: what must be true before this runbook is used

The identity-rewriting logic is proven at the logic level: the planning functions
are covered by unit tests that run without a site, and those tests pass. They are
part of the maintainer's own suite and do not ship with this repository, so a
clone cannot re-run them and this page is the only record that they exist. What is
**not** proven is the operator sequence around them.

On **31 July 2026** the full sequence was walked against a live pre-rename site
and could not be completed. Blockers B1 and B2 at the top of this page are the
outcome. This section stays as the acceptance test for lifting the deferral.

**Both blockers must be closed first.**

- **B1** — a supported way to invoke `preview_registry`, `diagnose` and
  `cutover` on a site that does not yet list `apex` among its installed apps.
  Until then the entry points are unreachable at the only moment they are
  needed.
- **B2** — a supported way to make an edited `sites/apps.txt` take effect on a
  site whose hooks cannot be loaded, given that `bench clear-cache` fails there.

**Then rehearse.** On a disposable bench, create a site and install the
application as it was packaged **before** the rename — a source tree whose own
package directory is `apex_habitat/` and carries the modules. Read
[the pre-rename source this repository does not hold](#the-pre-rename-source-this-repository-does-not-hold)
first: that tree is not in this history.

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

1. Before Section 4, `bench --site rehearsal.localhost migrate` fails with
   `Could not find app "apex_habitat"`. This confirms the rehearsal really
   started from the broken state, rather than from an already-canonical site.
2. `preview_registry` runs and prints the corrected registry text **on that
   still-broken site**, without an `AppNotInstalledError`. This is the direct
   test of B1; it is the observation that failed on 31 July 2026.
3. After the registry is written, the site reads the new file without any step
   outside this runbook. This is the direct test of B2; it also failed.
4. After Section 4 and before Section 5, `diagnose` returns `registry_state`
   `canonical` and a `next_step` key is **absent**.
5. Section 5's `cutover` returns `installed_apps: 1` and a `dotted_paths` entry
   for `tabNumber Card` / `method` with `rows` at least 1.
6. Re-running `cutover` immediately returns `installed_apps: 0`,
   `module_def: 0`, `installed_application: 0` and `dotted_paths: []`, proving
   idempotence.
7. Section 6's `bench migrate` completes with no `apex_habitat` message. Record
   how long it takes and how many patches it replays — that figure is the
   maintenance window a real site needs.
8. The seeded Number Card `method` now reads
   `apex.habitat.api.dashboard.probe`.
9. `SELECT defvalue FROM tabDefaultValue WHERE defkey='installed_apps'` contains
   `"apex"` exactly once and `"apex_habitat"` zero times.
10. The patch-history table still contains its historical `apex_habitat.*` patch
    names — the sweep deliberately skips audit tables, and rewriting
    applied-patch history would falsify the migration record. This is correct
    behaviour and is also the cause of the replay in observation 7.
11. Every command in Sections 1 through 6 exits `0` on its expected result, so
    the sequence can be followed under `set -e` without aborting on success.
12. The desk loads and an application workspace opens.

### The pre-rename source this repository does not hold

This repository cannot supply the starting state the rehearsal begins from. Its
first commit already carries the canonical `apex` package, and the
`apex_habitat/` directory that exists from there until the bridge was retired
holds four files — `__init__.py`, `bootstrap.py`, `hooks.py`, `modules.txt`. The
`__init__.py` describes itself as a temporary compatibility package and the
`hooks.py` declares a single `before_migrate` entry. That is the bridge which
used to perform the cutover during migrate, not the application. Installing it
yields a site carrying a shim beside `apex`, which is not a pre-rename site.

```bash
git rev-list --max-parents=0 HEAD            # the first commit already ships `apex`
git show <retirement-commit>^:apex_habitat   # four files, not an application
```

So the rehearsal has a prerequisite beyond B1 and B2: a genuine pre-rename
source, recovered from a deployment artifact of that era rather than from this
history. Until one is in hand none of the observations above can be recorded,
and closing B1 and B2 does not change that.

### What has been verified, and what has not

The steps that do not need the pre-rename state have been run end to end against
a site whose identity is already `apex`, and behave as documented:

| Step | Observed |
| --- | --- |
| 1 (a) | one `apex` line in `sites/apps.txt` — the "already canonical, stop" row |
| 1 (b) | `["frappe", "erpnext", "hrms", "apex"]` |
| 3 | `list-apps` prints a row naming `apex` and its version; exit `0` |
| 4 `preview_registry` | prints the registry unchanged; exit `0` |
| 5 `diagnose` | `registry_state` `canonical`, `installed_apps_legacy` `false`, `module_def_rows`, `installed_application_rows` and `legacy_method_rows` all `0`; exit `0` |
| 5 `cutover` | `{"installed_apps": 0, "module_def": 0, "installed_application": 0, "dotted_paths": []}`; exit `0`. This is the all-zero return observation 6 asks for, but reached from an already-canonical site rather than from a completed cutover, so it shows the no-op path, not idempotence after a real write |

Blocker B1's mechanism is confirmed without a pre-rename site, by invoking any
dotted path whose leading name is an app present on the bench but absent from
that site's installed apps — the condition `apex` is in before the cutover:

```
frappe.exceptions.AppNotInstalledError: App <name> is not installed
During handling of the above exception, another exception occurred:
NameError: name '<name>' is not defined
```

That is the pair Section 4 predicts. `bench execute` calls
`frappe.get_attr(method)` and falls back to `eval` on any exception
(`frappe/commands/utils.py:269,272`), so the second error is the fallback
failing on a name the first never imported.

Unverified, because each needs the site to be genuinely pre-rename: Section 4's
registry repair and its cache drop, Section 5's first write, Section 6's migrate
and patch replay, observations 1 to 5 and 7 to 12 above, and the part of
observation 6 that has to follow a cutover which actually wrote.

B2 need not be solved from nothing. The retired bridge dropped the cached
registry itself, deleting the app-discovery cache keys — `app_hooks`,
`installed_apps`, `all_apps`, `app_modules`, `installed_app_modules`,
`module_app`, `module_installed_app` — and rebuilding the module map afterwards.
That is one route to a supported cache drop, recorded as a starting point rather
than as a decision.

Record the observed output of each step. Any divergence is a defect in this
runbook, not an operator error. Update the status block at the top of this page
when, and only when, every observation above has been met.
