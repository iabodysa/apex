# Workspace Design: Task-First Information Architecture

Apex's operational workspaces follow one repeatable layout: orient the user once,
show the headline trend, then the day's actions, then what the role watches, then
reference data. This page documents the method so a new workspace can be built the
same way, and records the layout the shipped workspaces actually use.

## 1. What ships

Nine public Workspaces ship as `is_standard` JSON. They live beside the module
that owns them — `apex/habitat/workspace/<name>/<name>.json` and
`apex/salis/workspace/<name>/<name>.json`. There is no workspace directory under
`apex/apex_core/`.

| Workspace | Module | Parent | `sequence_id` | Roles |
|---|---|---|---|---|
| **Habitat** | Habitat | — (root) | `2.0` | Accommodation Manager, Finance Manager, Resident Supervisor, Cleaning Supervisor, Safety Officer, Maintenance Technician, Internal Auditor, SIM Operations User, System Manager, Fleet Manager, Administrator |
| **Housing** | Habitat | Habitat | `2.1` | Accommodation Manager, Cleaning Supervisor, Resident Supervisor, System Manager |
| **Safety** | Habitat | Habitat | `2.2` | Accommodation Manager, Resident Supervisor, Safety Officer, Maintenance Technician, Cleaning Supervisor, Internal Auditor, System Manager |
| **Custody** | Habitat | Habitat | `2.3` | Accommodation Manager, Resident Supervisor, SIM Operations User, System Manager |
| **Costs and Leasing** | Habitat | Habitat | `2.4` | Finance Manager, Accommodation Manager, System Manager |
| **Salis** | Salis | — (root) | `3.0` | Finance Manager, Fleet Manager, Fleet Project Manager, Fleet Supervisor, Government Relations Officer, Internal Auditor, System Manager |
| **Compliance and Rentals** | Salis | Salis | `3.2` | Fleet Manager, Fleet Supervisor, Finance Manager, Government Relations Officer, Internal Auditor, System Manager |
| **Fleet** | Salis | Salis | `4.0` | Fleet Manager, Fleet Project Manager, Fleet Supervisor, System Manager |
| **Backend Engines** | Habitat | — (root, `is_hidden`) | `90.1` | System Manager |

Two module roots, six children, and one hidden root. **Backend Engines** is hidden
because its ledgers and snapshots are system-written and read-only; it is reachable
only by System Manager and only by direct navigation.

Workspaces are **module-scoped, not role-named**. A role reaches its daily work
through the module workspace its roles grant it, not through a workspace named
after the role. Logistay ships no workspace at all — its surface is the **Telecom
Control** Desk page, and the **Custody** workspace is the single navigation host
for it and for the rest of the telecom links, cards, and reports. That is why
Custody grants `SIM Operations User`: a SIM in an employee's hands is a custody
record, so it is reached beside the other company property an employee holds,
while the module that owns the data stays Logistay. Do not read the Custody
placement as the telecom surface having moved modules — nothing telecom-owned
declares a module other than Logistay.

Two landing Workspaces, **Launchpad** and **My Work**, were retired during
workspace consolidation: the Launchpad's onboarding, settings, and logs folded
into the Habitat root, and the personal **Action Inbox** became a shortcut on both
module roots. `apex/patches/v2_0/remove_kernel_landing_workspaces.py` deletes the
two orphaned rows on migrate, clears any user still pinned to one, and pins
Backend Engines hidden.

## 2. The block spine

Every shipped workspace lays its `content` blocks out in the same order, top to
bottom. Headers are the section markers; each is followed by the blocks it labels.

| # | Header | Blocks under it | Why it goes here |
|---|--------|-----------------|-------------------|
| 0 | `Getting Started` | One `onboarding` block. | Oriented once, then ignored. |
| — | *(no header)* | One `chart`, immediately after the onboarding block. | The single headline trend, visible without scrolling. |
| 1 | `Quick Actions` | `shortcut` blocks — the role's most-used create screens, boards, and portals. | One click to the day's first task. |
| 2 | `Key Metrics` | `number_card` blocks. | Live numbers the role reacts to. |
| 3 | `Daily Tasks` | `card` blocks of input DocTypes the role creates or edits every day. | The role's actual job, not master data. |
| 4 | `Key Reports` | `card` blocks of reports and dashboards. | Periodic, read-only; ranked below live numbers. |
| 5 | `Master Data` | One `card` of reference DocTypes. | Configuration, not a task — so it goes last. |

The ordering rule is fixed: **Getting Started → chart → Quick Actions → Key
Metrics → Daily Tasks → Key Reports → Master Data.** Master data is last wherever
it appears.

Four shipped variations are deliberate, not drift:

- **Costs and Leasing** has no onboarding, so it opens directly on its chart.
- **Safety** carries two onboarding blocks (`Safety Readiness` and
  `Maintenance Daily Flow`) because it hosts two distinct daily flows.
- **Habitat** (the module root) names its first header `Habitat` rather than
  `Getting Started`, and appends a final `Setup` section after `Master Data`.
- **Backend Engines** is a flat list — one header and seven cards. It is a
  read-only System Manager utility, not a daily-work surface, so the spine does
  not apply.

**Compliance and Rentals** ships no `Master Data` section: its reference records
sit on the **Fleet** workspace instead, `Rental Office` among them.

Onboardings in use: `Apex Setup` (Habitat), `Accommodation Go-Live` (Housing),
`Safety Readiness` + `Maintenance Daily Flow` (Safety), `Custody Go-Live`
(Custody), `Masar Go-Live` (Salis), `Salis Fuel Setup` (Fleet), and
`Compliance and Rentals Go-Live`.

## 3. Surface-type conventions

A workspace mixes several kinds of link: a form you fill in, a live board, a
dashboard, a portal, a read-only report. Two conventions make the type obvious
without opening the link.

### Card-break legends

The `description` under each `Card Break` states in plain language what that group
of links does. Reuse these exact strings so a new section inherits the existing
`apex/translations/ar.csv` entries instead of adding untranslated ones:

| Section | Legend |
|---------|--------|
| Daily Tasks | `Input screen: open an item to create or edit records.` |
| Key Reports | `Reports: read-only. Open to view on screen or export.` |
| Dashboards | `Dashboards: live monitoring boards that refresh automatically.` |
| Master Data | `Reference data: durable records you set up once, not daily work.` |
| Setup | `Configuration and access: settings, users and roles.` |
| Logs | `System logs: read-only diagnostics.` |
| Portal-Managed Records | `Records created and managed through the resident / worker / driver portals. Admin visibility only.` |

### Label suffix tags

A shortcut or link whose type could be mistaken for a plain form carries a
parenthetical English tag in its label. The tag is part of the source string, so
each tagged label needs its own row in `apex/translations/ar.csv`.

| Tag | Meaning | In use today |
|-----|---------|--------------|
| `(Board)` | A live monitoring board or Desk page. | `Safety Map (Board)`, `Operations Control (Board)` |
| `(Dashboard)` | A Frappe Dashboard (charts and number cards). | none |
| `(Portal)` | A portal page. | none |

A plain DocType link (a form) carries no suffix — untagged is the default "input
screen" case.

> **Known gap.** Only `(Board)` is applied today. The portal shortcuts ship
> untagged (`Fleet Portal`, `Housing Portal`, `Safety Checklist`, `Inventory
> Count`), and `ar.csv` still carries translations for two tagged labels that no
> workspace uses (`Fleet Portal (Portal)`, `Fleet Supervisor Dashboard
> (Dashboard)`). Applying the tag to those shortcuts, or retiring the orphaned
> rows, is outstanding work.

### `(Portal)` — what a portal link actually is

A portal page is a Vue single-page app built to `apex/public/<portal>/` and served
by a Jinja shell in `apex/www/`. It is not a Desk page: it has its own
authentication path, its own bundle, and its own audience — a personal-token
worker app for people who are not Frappe users, or a session- and role-gated
operator surface. The seven served routes, their audiences, and their
authentication paths are listed once in
[Served portal routes](../README.md#served-portal-routes).

Portal shortcuts that ship on a workspace today:

| Workspace | Shortcut label | URL | Portal it opens |
|---|---|---|---|
| Fleet | `Fleet Portal` | `/fleet-os` | Fleet OS supervisor board |
| Housing | `Housing Portal` | `/housing` | Housing operator portal |
| Housing | `Inventory Count` | `/housing-count` | Redirect into the Housing portal's count view |
| Safety | `Safety Checklist` | `/safety` | Safety operator portal |
| Salis | `Worker Route (Masar)` | `/masar` | Worker PWA, for a supervisor checking what a worker sees |

The **Fleet** workspace is role-gated to the fleet team, so its portal shortcut
targets the supervisor board at `/fleet-os` rather than the employee page at
`/fleet`. The employee page needs no workspace shortcut: it is open to every
signed-in user and is reached from the `My Fleet` tile on the `/apps` selector.

> **Known gap.** No workspace links `/masar-supervisor`. Route supervisors reach
> it from its `Masar Supervisor` tile on the `/apps` selector or a typed URL. A
> Quick Actions shortcut on a movement workspace is the missing piece.

## 4. How a user lands on the right workspace

Two native primitives do the work. There is no provisioning patch that stamps
`User.default_workspace`, and none is needed.

1. **`roles`** — each Workspace lists the roles that may see it. A user sees only
   the workspaces their roles grant, so the sidebar is already filtered to their
   job. Leaving `roles` empty makes a workspace universal.
2. **`sequence_id` ordering** — `sequence_id` sorts the Desk sidebar. Apex uses
   `2.x` for Habitat and its children, `3.x`/`4.0` for Salis and its children, and
   `90.1` for the hidden Backend Engines, so operational surfaces sort above
   utilities.
3. **`parent_page`** — a child workspace names its root, which nests it under that
   root in the sidebar rather than adding another top-level entry.

A user may still pin any workspace they can see as their own default through their
User record; nothing in Apex overwrites that choice.

## 5. Reproducing this for a new workspace

1. Create a public, `is_standard` Workspace under the owning module's
   `workspace/` directory — `apex/habitat/workspace/` or `apex/salis/workspace/`.
2. List the roles that should see it in `roles`. Leave it empty only if the
   workspace is genuinely universal.
3. Set `parent_page` to its module root, and give it a `sequence_id` inside that
   root's band (`2.x` for Habitat, `3.x`/`4.x` for Salis).
4. Build the `content` blocks in the Section 2 order: Getting Started
   (onboarding) → chart → Quick Actions (shortcuts) → Key Metrics (number cards)
   → Daily Tasks (cards) → Key Reports (cards) → Master Data (card).
5. Add a `Card Break` per section, reusing the exact legend strings from Section 3
   so they inherit the existing `ar.csv` translations.
6. Tag any Board, Dashboard, or Portal shortcut label with the matching suffix and
   add the Arabic translation to `apex/translations/ar.csv` if the label is new.
7. Remember that `is_standard` JSON is import-only on migrate. Deleting or
   renaming a workspace file leaves the old row and its child Link, Shortcut,
   Number Card, and Chart rows in the database — that removal needs its own
   patch, the way `remove_kernel_landing_workspaces.py` handled Launchpad and
   My Work.

## 6. Keeping this page honest

Section 1 is a published description of a directory, and its `Roles` column is a
published description of who can reach each workspace. Both are checked by
`apex/tests/test_workspace_doc_parity.py`, which runs in CI: it parses the table
above, reads every shipped workspace JSON, and fails the build when the two
disagree on the workspace set, the roles granted, the owning module, the parent,
the `sequence_id`, or the `is_hidden` annotation. Run it directly with:

```bash
python3 -m unittest apex.tests.test_workspace_doc_parity -v
```

A role added to a workspace JSON therefore cannot ship until this table names it.

The portal route table in
[README.md](../README.md#keeping-the-route-table-honest) still relies on the
manual shell check documented there; it has no equivalent automated guard yet.
