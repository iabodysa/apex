# Workspace Design: Task-First Information Architecture

Apex's operational workspaces follow one repeatable layout: open on the role's
daily work, then monitoring, then reference data — never the reverse. This
page documents the method so a new daily-role workspace can be built the same
way. It was introduced by the four daily role workspaces (Resident Supervisor,
Fleet Supervisor, Safety Officer, Maintenance Technician).

## 1. The three-section spine

Every daily-role workspace is built as three sections, top to bottom, with a
short onboarding block above them:

| # | Section | Content | Why it goes here |
|---|---------|---------|-------------------|
| 0 | Getting Started (optional) | An onboarding checklist for the role's first login. | Oriented once, then ignored. |
| — | Quick Actions | Shortcuts to the role's most-used create screens and boards/portals. | One click to the day's first task. |
| 1 | Daily Tasks | Input DocTypes the role creates or edits every day ("Create Records"). | The role's actual job comes first, not master data. |
| 2 | Monitoring | Key-metric number cards, one trend chart, then boards/dashboards, then reports. | What the role watches and reacts to, ranked by how often they look at it: live numbers → live board/dashboard → periodic report. |
| 3 | Master Data | Reference DocTypes (buildings, vehicles, item masters, etc.) set up once, not daily work. | Always last — it is configuration, not a task. |

In the underlying Workspace `content` layout this is four headers in order —
`Daily Tasks`, `Key Metrics` (+ 1 chart), `Boards and Dashboards`/`Monitoring`,
`Key Reports`, `Master Data` — each followed by its `card`/`number_card`/`chart`
block. A role with few boards/reports may merge the monitoring sub-headers
into a single `Monitoring` header (see the Maintenance Technician example),
but the ordering rule is fixed: **Daily Tasks → Monitoring (metrics, chart,
boards, reports) → Master Data**, master data always last.

## 2. Surface-type tags

A workspace mixes several kinds of link: a form you fill in, a live board, a
dashboard, a portal, a read-only report. Two conventions make the type
obvious without opening the link:

- **Card-break legends** — the description under each `Card Break` states in
  plain language what that group of links does, e.g. `Input screen: open an
  item to create or edit records.` (Daily Tasks), `Monitoring boards and
  dashboards: live views that refresh automatically.`, `Reports: read-only.
  Open to view on screen or export.`, `Reference data: durable records you set
  up once, not daily work.` (Master Data).
- **Label suffix tags** — any shortcut or link whose type could be mistaken
  for a plain form carries a parenthetical English tag in its label, translated
  to Arabic in `translations/ar.csv`:

  | Tag | Meaning | Arabic |
  |-----|---------|--------|
  | `(Board)` | A live monitoring board/desk page. | `(لوحة متابعة)` |
  | `(Dashboard)` | A Frappe Dashboard (charts + number cards). | `(لوحة معلومات)` |
  | `(Portal)` | An external/worker-facing portal page. | `(بوابة)` |

  Example: `Fleet Portal (Portal)` → `بوابة الأسطول (بوابة)`,
  `Fleet Supervisor Dashboard (Dashboard)` → `لوحة معلومات مشرف الأسطول (لوحة معلومات)`.
  A plain DocType link (a form) carries no suffix — untagged is the default
  "input screen" case.

## 3. Default-workspace mechanism

Two independent primitives combine to make the role's daily workspace the
first thing a user in that role sees:

1. **`sequence_id` ordering** — each daily-role Workspace sets a low
   `sequence_id` (`1.0`–`1.3` for the four roles below) so it sorts near the
   top of the Desk sidebar, ahead of the generic `Launchpad` (`90.0`) and
   other module workspaces.
2. **`User.default_workspace` provisioning patch** —
   `apex/patches/v2_0/set_role_default_workspace.py`
   (registered in `patches.txt` as
   `apex.patches.v2_0.set_role_default_workspace`) is a guarded,
   idempotent, run-once patch. For each of the four roles it finds every user
   holding that role and, **only if `default_workspace` is still empty**,
   stamps it to the role's workspace. It never overwrites a workspace the
   user picked for themselves, and it skips a role whose workspace row is not
   yet present (safe to land before the workspace JSON ships). `sequence_id`
   makes the workspace easy to find manually; the patch makes it the page a
   user actually lands on after login.

To extend this to a fifth role: add its workspace name to `ROLE_WORKSPACE` in
that patch (a **new** run-once patch is the right pattern if the original one
has already run on deployed sites — see the module's `PRUNE` note) and give
the workspace a `sequence_id` in the `1.x` range.

## 4. Worked examples

The four daily role workspaces shipped under `apex/apex_core/workspace/`:

| Workspace | `sequence_id` | Daily Tasks (Create Records) | Monitoring | Master Data |
|---|---|---|---|---|
| **Resident Supervisor** | `1.0` | Housing Assignment, Housing Checkout, Resident Request, Room Bed Transfer, Cleaning Log, Custody Issue, Custody Return | 4 number cards + Occupancy Percent Trend chart; boards: Front Desk, Arrivals Desk, Custody Kiosk, Room Setup; dashboard: Resident Supervisor Dashboard; reports: Active Resident Register, Idle Resident Detection, Custody Outstanding by Worker | Building, Room, Bed, Site |
| **Fleet Supervisor** | `1.1` | Vehicle Assignment, Vehicle Handover, Fuel Request, Vehicle Incident | 5 number cards + Fuel Cost by Month chart; board: Fleet Control; portal: Fleet Portal; dashboard: Fleet Supervisor Dashboard | vehicle/fleet master records |
| **Safety Officer** | `1.2` | Safety Round, Safety Incident, Safety Task Execution | 5 number cards + Findings by Severity chart; board: Safety Map; portal: Safety Portal | safety master records |
| **Maintenance Technician** | `1.3` | Maintenance Request, Maintenance Work Order, Maintenance Inspection Report, Facility Asset, Facility Asset Movement, Subcontractor Service Order | 4 number cards + Maintenance Requests by Status chart; monitoring list: Operations Alert, Scheduled Task Instance; reports: Open Maintenance Requests, Maintenance Aging, Operational Depreciation Aging | Maintenance Material, Maintenance Material Template, Subcontractor Service Contract |

Each also carries a role-specific onboarding (e.g. `Accommodation Go-Live`,
`Maintenance Daily Flow`) as the first "Getting Started" block, and Quick
Action shortcuts that jump straight to the role's top 1–2 create screens plus
its board/portal.

## 5. Reproducing this for a new role

1. Create a public, `is_standard` Workspace scoped to the role (plus any
   manager/System Manager roles that should also see it).
2. Set `sequence_id` in the `1.x` range, below the four existing daily
   workspaces if it is a fifth peer, or interleaved if it takes priority.
3. Build the `content` blocks in order: Getting Started (onboarding) → Quick
   Actions (shortcuts) → Daily Tasks (`Create Records` card) → Key Metrics
   (number cards + one chart) → Monitoring/Boards and Dashboards → Key
   Reports → Master Data.
4. Add a `Card Break` per section with the matching legend description from
   Section 2 above (reuse the existing English strings so they inherit the
   existing `ar.csv` translations).
5. Tag any Board/Dashboard/Portal shortcut or link label with the matching
   `(Board)` / `(Dashboard)` / `(Portal)` suffix, and add the Arabic
   translation to `translations/ar.csv` if it is a new label.
6. Add the role → workspace mapping to `ROLE_WORKSPACE` in
   `apex/patches/v2_0/set_role_default_workspace.py` (or a new
   patch, per its `PRUNE` note) so the workspace becomes the role's default
   landing page.
