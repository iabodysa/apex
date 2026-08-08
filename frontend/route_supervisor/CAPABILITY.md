# /masar-supervisor — capability

The screen where a route supervisor decides on the bus route plans handed to him, then watches
the trips those plans produced actually run.

Bundle `route_supervisor_portal`, built from `frontend/route_supervisor`, served by
`apex/www/masar_supervisor.py` + `apex/www/masar-supervisor.html`, backed by
`apex.salis.api.route_supervisor`.

---

## 1. What it does

Three whole-screen destinations, and inside one of them four per-plan views.

| Screen | Reached by | The decision or task it serves |
|---|---|---|
| Assigned plans (list + detail) | `#/` and `#/plan/<name>/<tab>` | Which of my plans still needs a decision, and what is each one? |
| Approvals queue | `#/approvals` | Decide the pending ones in a row, without opening each plan. |
| All drivers map | `#/map` | Where is every one of my drivers right now, together, on one map. |

Inside a selected plan (`frontend/route_supervisor/src/App.vue:259-264`):

| View | The decision or task it serves |
|---|---|
| Approval | Approve or reject this plan; a rejection must carry a written reason. |
| Boarding | Is this trip filling up — boarded vs expected, and who is still waiting. |
| Route | Are the ordered stops, times and passenger counts right before I approve. |
| Live map | Where is this plan's driver, and is the position fresh or frozen. |

The "Live map" view is withdrawn as a tab above 1280px, because the same live map is already
drawn beside the plan at that width (`App.vue:209`, `App.vue:214-216`, `App.vue:389`). A shared
link that names `map` while the reader is on a wide screen is rewritten to the first tab rather
than landing on nothing (`App.vue:396-401`).

**No screen here exists without a job.** Every view answers a question the supervisor has to
answer before or during a dispatch.

---

## 2. How it works

All seven endpoints live in `apex/salis/api/route_supervisor.py`. All seven carry
`@frappe.whitelist()`; the two writes additionally carry `methods=["POST"]`. **None is missing
its decorator.** Paths are declared once as constants and composed by concatenation in
`frontend/route_supervisor/src/api.js:6-10` (`API + "." + method`) — a rebuild that greps for
literal dotted paths will find none of them.

| Dotted path | Sends | Does with the answer | Called from |
|---|---|---|---|
| `apex.salis.api.route_supervisor.get_supervisor_context` | nothing | Replaces the whole plan list, the pending/total counters, and the supervisor's own name; then picks a plan only if a plan is what the screen is showing | `App.vue:428-451` |
| `…get_route_stops` | `route_plan` | Renders the ordered stops of one plan | `components/RoutePanel.vue:61-72` |
| `…get_trip_boarding` | `dispatch_trip` | Renders boarded/expected, the per-status breakdown, and the per-worker list | `components/BoardingPanel.vue:115-129` |
| `…get_trip_driver_position` | `dispatch_trip` | Moves one map marker; `has_position` false draws the "no fix yet" state instead of a marker at (0,0); `stale` dims it | `components/DriverMap.vue:132-151` |
| `…get_active_driver_positions` | nothing | Draws every driver marker plus each plan's road path, and fills the driver/plan filter lists | `components/FleetMap.vue:192-204` |
| `…approve_route_plan` (POST) | `name` | Toast, then a full context reload | `App.vue:453-466` |
| `…reject_route_plan` (POST) | `name`, `reason` | Toast, close dialog, then a full context reload | `App.vue:475-493` |

Polling, all client-side and all independent:

| What | Interval | Guard |
|---|---|---|
| Whole context | 45 s (`App.vue:341`, via `frontend_shared/usePoll.js`) | skipped while a write is in flight or the reject dialog is open; stops entirely when the tab is hidden |
| Boarding | 15 s (`BoardingPanel.vue:84`) | skipped when hidden, or when that view is not the active one |
| One driver position | 10 s (`DriverMap.vue:82`) | same |
| All driver positions | 15 s (`FleetMap.vue:81`) | skipped when hidden only |

Note for the rebuild: the per-view components are kept mounted and merely hidden, so their
first fetch fires the moment a plan is selected regardless of which view is open
(`App.vue:207-209`; `BoardingPanel.vue:159-163`, `RoutePanel.vue:81`). Only the *repeat* poll
respects the active view.

---

## 3. Who opens it

**Identity model: a logged-in Frappe User.** No token, no cookie subject. The row boundary is
`Route Plan.route_supervisor == frappe.session.user`.

The gate, from `apex/www/masar_supervisor.py`:

- Guests are redirected, never refused: `guest_redirect("/masar-supervisor")` (line 96) sends
  them to `/login?redirect-to=/masar-supervisor` (`apex/apex_core/utils/portal_bootstrap.py:45-47`).
- A logged-in user without a role gets an explanatory page, not a 403:
  `context.has_supervisor_role = bool(SUPERVISOR_ROLES & set(frappe.get_roles()))` (line 102),
  and `masar-supervisor.html:27-34` swaps the app mount for a denial include. The SPA bundle,
  the CSRF token, the socket config and the map-tile config are **not emitted at all** for such
  a user (`masar-supervisor.html:10-24`) — the gate is not a hidden `<div>`.
- Required roles (`masar_supervisor.py:69-74`): `System Manager`, `Fleet Manager`,
  `Fleet Project Manager`, `Fleet Supervisor`.
- The `/apps` tile reuses the page's own set so a tile can never show for a user the page turns
  away (`masar_supervisor.py:87-91`).

**Scoped server-side, not in the browser.** The role check is a coarse door. Every read and both
writes re-derive scope on the server:

- `_require_portal_role()` (`route_supervisor.py:64-71`) throws `PermissionError` for a caller
  without a role — so the API is safe even if the page were bypassed.
- `_owned_plan(name)` (lines 79-114) fails closed with `PermissionError` when
  `plan.route_supervisor != session user`; `_owned_trip()` (117-144) resolves a trip to its plan
  and runs the same guard, so trip-level reads inherit plan-level scope exactly.
- The list reads filter on `route_supervisor` in SQL, not after the fact
  (lines 358-360, 555-557), and only `docstatus == 1` — a draft plan has not been handed over yet.
- `Administrator` is the sole bypass, deliberately, for seeding and verification (lines 74-76).
- Writes add lifecycle preconditions on top of ownership (`_resolve_owned_plan_doc`, lines
  641-661): submitted only, and Pending only — a decided plan cannot be re-decided.

`render_in_arabic()` (line 99) forces `frappe.local.lang = "ar"` for the render, because the
shell declares `lang="ar" dir="rtl"`; without it, English sentences land inside an RTL box and
the full stop appears at the start of the line
(`apex/apex_core/utils/portal_language.py:2-12`).

Controller filename is load-bearing: Frappe resolves `masar-supervisor.html` to
`masar_supervisor.py` by hyphen→underscore. A hyphenated `.py` is never imported, `get_context`
never runs, and **every** user falls to the "no role" branch.

---

## 4. What is required of it

The supervisor must finish these, on this screen:

1. **Decide every plan handed to him.** Approve it, or reject it with a reason the planner can
   act on. A rejection without a reason is refused, on the client and again on the server.
2. **Not decide blind.** Before approving he can read the plan's ordered stops, its times, its
   expected passengers, and which driver and vehicle are on it.
3. **Clear the backlog quickly.** Approve or reject straight from the waiting list without
   losing his place in it.
4. **Watch the trip run.** See boarding fill up against the expected headcount, and see where
   the driver is — including being told plainly that there is no position yet, or that the last
   position is old.
5. **See all his drivers at once**, filtered by driver or by plan, when he is running a yard.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what |
|---|---|---|
| Server-side gating | **Yes** | `_require_portal_role()` on all seven endpoints. The role list is duplicated in `www/masar_supervisor.py:69-74` and `api/route_supervisor.py:37-42` — a rebuild must keep them equal or make them one constant. |
| Row scoping | **Yes** | `route_supervisor == session user`, enforced in SQL for lists and via `_owned_plan`/`_owned_trip` for every single-record read and both writes. Never trust a `name` from the client. |
| CSRF propagation | **Yes** | `window.csrf_token` is set by the template (`masar-supervisor.html:15`) and read by frappe-ui, which sets `X-Frappe-CSRF-Token` (`frappe-ui/src/utils/frappeRequest.js:19`). The two POSTs fail without it. |
| Realtime rooms + teardown | **Declared, and currently dead — see Defects.** | Intent: subscribe to the `Route Plan` doctype room, listen for `route_plan_decision`, refetch. Publisher exists (`apex/salis/doctype/route_plan/route_plan.py:68-73`, `after_commit=True`). Teardown emits `doctype_unsubscribe`, removes the handler and disconnects (`frontend_shared/realtime.js:68-76`), wired to `onUnmounted` (`App.vue:527`). Keep the *shape*; fix the wiring. |
| URL state | **Yes, and it is the whole navigation model** | `#/`, `#/plan/<encoded name>/<tab>`, `#/approvals`, `#/map`. Refresh, Back and a pasted link all resolve. Two `hashchange` + two `popstate` listeners re-derive the view and are removed on unmount (`App.vue:512-526`). Selection and tab are pushed, never replaced (`App.vue:404-410`). |
| Offline behaviour | **No** | There is no service worker, no cache and no queue in this portal. A failed load shows a retry; a failed action shows a toast. Do not invent offline support in the rebuild; do keep the retry paths. |
| Language propagation | **Yes, two halves** | Server: `render_in_arabic()` pins the *shell* to Arabic. Client: the toggle writes `<html lang>`/`dir` (`frontend_shared/useDocumentLanguage.js`), and every request appends `_lang` from that attribute (`frontend_shared/call.js:12-16`). `_lang` is the **first** source Frappe consults (`frappe/translate.py:46-47`), so server-thrown messages come back in the language on screen. Preference persists under `masar_supervisor_lang`. |

### The menu invariant (do not re-derive the patch — keep the rule)

The side menu holds two kinds of item: the tabs of the open plan, and the whole-screen
destinations. Both used to own "which item is current" separately, so two lit at once and
re-tapping the current tab did nothing.

**The invariant a rebuild must satisfy:**

1. The address bar is the **only** writer of "which whole-screen destination am I on"
   (`App.vue:277-284`). Nothing else may set those flags.
2. A plan tab is current **only** while a plan is what the screen is showing — one derived flag,
   not a second copy of the state (`App.vue:275`).
3. Selecting a tab must reconcile the URL **directly**, not by hoping a watcher fires. Assigning
   a ref its current value fires nothing; that is precisely why re-tapping the open tab did
   nothing while the queue stayed on screen (`App.vue:302-308`).
4. Navigation pushes only when the address actually changes, then re-derives the view from the
   address (`App.vue:286-292`).
5. Acting on a queue card must not move the selection — deciding a card that was not already
   selected used to throw the supervisor out of the queue (`App.vue:310-315`, `App.vue:329-332`,
   `App.vue:475-493` uses `rejecting` rather than the selection).
6. A background refresh may auto-pick a plan **only** while a plan is on screen; doing it on the
   queue or the map reads as an intent to navigate (`App.vue:439-445`).

---

## 6. What is deliberately dropped

| Dropped | Evidence |
|---|---|
| Nothing in `src/index.css`. | A full class sweep of `src/index.css` against every `.vue`/`.js` in this portal plus `frontend_shared` leaves only `bd-*`, `sb-*`, `st-*`, `toast-*` — all built at runtime by string concatenation (`App.vue:124`, `App.vue:183`, `BoardingPanel.vue:38`, `App.vue:233`). This portal's stylesheet is clean; do not "clean" it again. |
| The empty `errors: {}` namespace in both languages. | `src/i18n.js:131-132` and `257-258` — an empty object in each language. Safe to delete, but only because `createI18n` falls through to `frontend_shared/sharedMessages.js:8-20` on a miss (`frontend_shared/i18n.js:28-32`), which is where `errors.rateLimited` and `errors.sessionExpired` actually live. The shared error helper reaches for both keys (`frontend_shared/i18n.js:57-67`), so a rebuild must keep that fallback — delete the empty stub, never the shared table. |
| `agoLabel`'s hand-rolled unit table. | Already replaced by `Intl.RelativeTimeFormat` (`src/fmt.js:11-31`) because a `{n}` template cannot carry the Arabic dual. Do not regress to a template. |
| Nothing else. | Every component in `src/components/` is rendered from `App.vue`; every exported function in `src/fmt.js` and `src/api.js` has a caller. |

---

## Defects found while reading

1. **Realtime is silently dead in this portal.** The template publishes the socket config as
   `window.masar_sup_socket` (`apex/www/masar-supervisor.html:17`), but the client reads
   `window.route_supervisor_socket` (`frontend/route_supervisor/src/realtime.js:5`). The factory
   returns a no-op when `site` is empty (`frontend_shared/realtime.js:28`), so `connect` returns
   `() => {}` and no socket is ever opened. Confirmed in the shipped bundle: it contains
   `route_supervisor_socket` and not `masar_sup_socket`. Consequence — a plan decided elsewhere
   reaches this screen only on the 45 s poll, and the `route_plan_decision` publisher has no
   subscriber.

2. **The all-drivers map has no Leaflet fallback.** `DriverMap.vue:71-72` computes `hasLeaflet`
   and renders a coordinate readout when the library is missing. `FleetMap.vue:107-108` simply
   returns from `ensureMap()`, leaving a permanently blank canvas with no explanation. The
   documented degradation contract (`www/masar_supervisor.py:51-54`) is only half implemented.

3. **The all-drivers map has no tile-failure notice.** `DriverMap.vue:102-107` binds
   `tileerror`/`tileload` and surfaces "background unavailable". `FleetMap.vue:113` binds
   neither.

4. **Duplicate `v-for` keys in the plan filter.** `FleetMap.vue:103-105` maps rows straight to
   `{ name: row.route_plan }` with no de-duplication, while `driverNames` (100-102) does
   de-duplicate. Two live trips on one route plan yield two options with the same `:key`.

5. **Boarding and route data are fetched for views the supervisor never opens.** Because the
   per-view components are `v-show`n rather than `v-if`d (`App.vue:207-208`), selecting any plan
   fires `get_trip_boarding` and `get_route_stops` immediately. On the queue-clearing path this
   is two wasted requests per plan opened.

6. **Two writers of the sort order in the payload path.** `_pending_first`
   (`api/route_supervisor.py:331-341`) re-sorts in Python because Frappe's order-by allowlist
   rejects `field()`. The comment records that the SQL form raised HTTP 417 on every request.
   Worth keeping as a warning: do not "optimise" this back into SQL.
