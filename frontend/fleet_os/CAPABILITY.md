# /fleet-os — capability

The one screen a fleet supervisor keeps open all day: every vehicle he is responsible for, what
state each is in, who is holding it, and the actions that change that state.

Bundle `fleet_os_portal`, built from `frontend/fleet_os`, served by `apex/www/fleet_os.py` +
`apex/www/fleet-os.html`, backed by `apex.salis.api.fleet_os` (read shape in
`apex.salis.api.fleet_os_board`) and `apex.salis.api.operations_alerts`.

This board is treated as a fallback but is **not** being retired. It is the only screen that
carries the bulk actions, the driver reassignment path and the per-vehicle incident record.

---

## 1. What it does

One screen. No routes, no tabs in the address bar — everything below is a state of the same page.

| Region | The decision or task it serves |
|---|---|
| Status counters | How many vehicles are assigned / available / in workshop / stopped / stolen — and each one is a filter, not a label (`src/App.vue:181-186`). |
| Triage counters | How many have an open incident, how many have a compliance document expiring — shown only when non-zero, and each toggles a filter (`App.vue:187-188`, `useFleetBoard.js:60-69`). |
| Filters | Narrow the fleet by type, project, area, rental office, fuel, and a date range over assignment receive/deliver dates (`components/FleetSidebar.vue`). |
| Search | One free-text box over plate, vehicle type, office, area and the current driver's names and id (`useFleetFilters.js:109-123`). |
| Three views of the same filtered set | cards, table, and a driver-grouped lens. The lens is capability-gated. |
| Selection + bulk bar | Stop, or send to workshop, many vehicles at once with one shared note. |
| Vehicle panel | Six sections on one vehicle: overview, driver, status, damages, accidents, log. This is where the single-vehicle actions live. |
| Alerts drawer | The open operations alerts, opened from a bell that carries a count. |

### Findings on what the screen shows

- **A hard-coded fuel price is presented as data.** `src/useFleetFormat.js:42` fixes
  `0.69 / 2.33 / 2.18` SAR per litre in the bundle, and `components/VehiclePanel.vue:65` renders
  it beside the grade as if it came from the server. `monDisplay` then multiplies the planned
  daily figure by a flat 30 (`useFleetFormat.js:49`). A rebuild must either read prices from a
  record or stop showing a currency figure.
- **`reader_errors` is returned by the server and thrown away.** `build_board()` collects
  per-section read failures (`apex/salis/api/fleet_os_board.py:362`, `384-391`) and returns them;
  `useFleetBoard.js:20-21` reads only `vehicles` and `reason`. A board that loaded with a section
  missing looks identical to one that loaded whole.
- **The table's sort state is invisible.** `components/FleetTable.vue:17-26` makes nine `<th>`s
  clickable, but nothing marks which column is sorting or in which direction, and no `aria-sort`
  is set. The direction lives in `sortDir` (`useFleetFilters.js:22`), which is never passed to the
  table.

---

## 2. How it works

Twelve endpoints. **Eleven** are in `apex/salis/api/fleet_os.py` and one is in
`apex/salis/api/operations_alerts.py:71-72`. All twelve carry `@frappe.whitelist()`; the nine
writes additionally carry `methods=["POST"]`. **None is missing its decorator.**

**Every fleet_os path is built by string concatenation.** `const POST = (m) =>
"apex.salis.api.fleet_os." + m;` appears twice — `src/useFleetActions.js:7` and
`src/useDriverAssignment.js:7` — and the board read is a module constant
`src/useFleetBoard.js:7`. Alerts use a module constant `src/useAlerts.js:5`. A rebuild grepping
for literal dotted paths finds **only two of the twelve**.

| Dotted path | Sends | Does with the answer | Called from |
|---|---|---|---|
| `apex.salis.api.fleet_os.get_fleet_os` | nothing | Replaces the whole vehicle array; keeps `reason` to distinguish "scoped to nothing" from "genuinely empty" | `useFleetBoard.js:16-38` |
| `apex.salis.api.operations_alerts.get_open_alerts` | nothing | Fills the drawer list and the bell count | `useAlerts.js:13-23` |
| `…fleet_os.search_drivers` (GET) | `q` | Fills the driver typeahead; the picker binds the canonical `name`, never free text | `useDriverAssignment.js:27` |
| `…reassign` (POST) | `plate`, `driver_id`, `date` | Toast, optional handover, close form, full board reload | `useDriverAssignment.js:71-74` |
| `…create_handover` (POST) | `plate`, `driver_id`, `date`, `odometer`, `checklist_template`, `condition_notes` | Optional follow-up to a reassign; its own failure downgrades to a warning and does **not** undo the reassign | `useDriverAssignment.js:78-96` |
| `…stop_vehicle` (POST) | `plate`, `reason` (reason and notes joined client-side) | Then optionally chains `workshop_in` or `recover`, then reload | `useFleetActions.js:50-57`, `:305` |
| `…workshop_in` (POST) | `plate` | Toast + reload | `useFleetActions.js:55`, `:127`, `:301` |
| `…workshop_out` (POST) | `plate` | Toast + reload | `useFleetActions.js:148`, `:303` |
| `…recover` (POST) | `plate` | Toast + reload | `useFleetActions.js:57`, `:169`, `:190`, `:303` |
| `…report_theft` (POST) | `plate`, `location`, `report_number` | Toast + reload | `useFleetActions.js:89-92` |
| `…bulk_stop_vehicles` (POST) | `plates[]`, `reason` | Shows a succeeded/failed summary, clears the selection, reloads | `useFleetActions.js:222-225` |
| `…bulk_workshop_in` (POST) | `plates[]`, `notes` | Same | `useFleetActions.js:246-249` |

Two whitelisted endpoints in the same module have **no caller anywhere in the repo**:
`get_status_meta` (`fleet_os.py:193`) and `get_vehicle_timeline` (`fleet_os.py:208`). The panel's
log section renders from the board payload instead (`components/VehiclePanel.vue:303` via
`fleetHelpers.js:38-42`).

Refresh model, from `src/App.vue:100-155`:

- 30 s poll, skipped when the tab is hidden **or** when paused.
- Paused when: the board is not `ready`, a confirmation is open, a sub-form is open, any
  per-vehicle action is in flight, or anything is selected. This is what stops a refresh
  destroying a half-typed form or a selection.
- Realtime arriving while paused sets `realtimePending` and is replayed the moment the pause
  lifts (`App.vue:126-138`) — a good pattern; keep it.
- `visibilitychange` triggers an immediate reload on return, or defers it if paused.
- Every path fetches the **whole** board; there is no delta.

---

## 3. Who opens it

**Identity model: a logged-in Frappe User holding a fleet role.** No token, no per-row ownership —
the boundary here is **project scope**, not "my records".

The gate, from `apex/www/fleet_os.py`:

- Guests are redirected: `guest_redirect("/fleet-os")` (line 45).
- A logged-in user without a role gets an explanatory page, not a 403:
  `context.has_fleet_role = bool(FLEET_ROLES & set(frappe.get_roles()))` (line 51), and
  `fleet-os.html:26-33` swaps the mount for a denial include. The bundle, the CSRF token, the
  socket config and the capability object are **not emitted at all** for such a user
  (`fleet-os.html:11-23`).
- Required roles (lines 28-33): `System Manager`, `Fleet Manager`, `Fleet Project Manager`,
  `Fleet Supervisor`. The `/apps` tile gate reuses the same set and **is** wired (lines 36-40) —
  unlike `/fleet`, whose identical helper is deliberately unwired.
- One capability is passed to the client: `context.fleet_caps = {"driver_lens": has_fleet_role}`
  (line 53) → `window.fleet_caps` → `App.vue:97-98`. Today it always equals the role check, so
  the driver lens is visible to every user who can open the page at all. It is a client-side
  **display** gate; the data it shows arrives in `get_fleet_os` regardless.

**Scoped server-side.** Two independent layers:

- **Permission:** every endpoint calls `frappe.has_permission("Salis Vehicle", …, throw=True)`
  (`fleet_os.py:117`) and every action resolves the plate through `_resolve_plate`, which
  permission-checks the resolved record with `ptype="write"` (`fleet_os.py:69-86`). A plate
  string from the client is never trusted as a record id.
- **Project scope:** `build_board()` calls `scope_filter()` and returns
  `{"vehicles": [], "reason": "scope_empty"}` when the user is scoped to no project
  (`fleet_os_board.py:363-365`). `search_drivers` applies the same `_permitted_projects` resolver
  (`fleet_os.py:136-138`). It is the same resolver the dispatch board and the list-view
  `permission_query_conditions` use, so the board can never widen what the desk already shows.
- **PII:** `driver_pii_visible()` blanks driver id and phone for a role without permlevel-1
  (`fleet_os.py:135`, `fleet_os_board.py:361`).

`render_in_arabic()` (line 48) pins the shell render to Arabic, matching `lang="ar" dir="rtl"` in
`fleet-os.html:3`.

Controller filename is load-bearing here too: the route is hyphenated (`/fleet-os` via
`www/fleet-os.html`) while the module must be underscored to be importable.

---

## 4. What is required of it

The supervisor must be able to finish these, on this board:

1. **Know the state of every vehicle he is responsible for**, at a glance, including which have
   an open incident and which have a document about to expire.
2. **Find one vehicle fast** — by plate, by driver, by office, by project, by area, by type.
3. **Hand a vehicle to a driver**, picking that driver from a real list rather than typing a
   name, and optionally record the handover condition at the same time.
4. **Take a vehicle out of service** — stop it and release its driver, send it to the workshop,
   bring it back — and say why.
5. **Report a vehicle stolen** with the police report number and location, and later recover it.
6. **Do 3-5 to a whole batch** when a rental office returns a group at once, and be told plainly
   how many succeeded and how many failed.
7. **See the open alerts** and jump from an alert to the vehicle it is about.
8. **Never act on a stale picture** — the board refuses to repaint under his hands while he is
   mid-action.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what |
|---|---|---|
| Server-side gating | **Yes** | Role gate on the page; `has_permission` on every endpoint; `_resolve_plate` permission-checks the resolved record before any write. The role list is duplicated in `www/fleet_os.py:28-33` and `www/fleet.py:27-32` — keep them equal or make them one constant. |
| Row scoping | **Yes, by project not by owner** | `scope_filter()` / `_permitted_projects()`, the same resolver as the desk. The typed `reason` (`scope_empty` vs `data_empty`) must survive — it is what tells a supervisor "you have no project" instead of "the fleet is empty". |
| CSRF propagation | **Yes** | `window.csrf_token` (`fleet-os.html:14`) → frappe-ui sets `X-Frappe-CSRF-Token` (`frappe-ui/src/utils/frappeRequest.js:19`). Nine POST endpoints depend on it. |
| Realtime rooms + teardown | **Yes, and it works here** | Room: the `Salis Vehicle` doctype room. Event: `fleet_update`, published `after_commit` by eight write paths (`apex/salis/api/fleet_os.py:47-58`). The socket server delivers only to recipients with read permission, so scope is honoured without extra filtering. The payload is **advisory only** — the client refetches via `get_fleet_os` and never trusts the message body. Teardown emits `doctype_unsubscribe`, removes the handler and disconnects (`frontend_shared/realtime.js:68-76`), wired to `onUnmounted` (`App.vue:151-155`) together with the poll timer and the `visibilitychange` listener. |
| URL state | **None at all — and that is the single biggest gap** | There is no router, no hash, no query string anywhere in `frontend/fleet_os/src/`. Filters, search, status pill, triage toggle, sort, view mode, density, selection, which vehicle panel is open, and whether the alerts drawer is open are all in-memory. A refresh, a Back press, or a link sent to a colleague loses every one of them. Only the density preference persists, in `localStorage` under `fleet_portal_density` (`useFleetFilters.js:217-233`). **A rebuild must put at least filters, view and the open vehicle in the URL** — the desk sibling already does exactly this (`apex/salis/page/operations_control/operations_control.js:270-273`). |
| Offline behaviour | **No** | No service worker, no cache, no queue. A failed background reload sets a stale banner and keeps the last good data on screen (`useFleetBoard.js:34-37`, `App.vue:218-222`) — that graceful-stale behaviour is worth keeping; offline is not a feature to invent. |
| Language propagation | **Yes** | Server: `render_in_arabic()`. Client: toggle → `<html lang>`/`dir` → `_lang` on every request (`frontend_shared/call.js:12-16`) → first source in `frappe/translate.py:46-47`. Sorting is locale-aware throughout (`localeCompare(…, "ar")` at `useFleetFilters.js:150`, `:172`, `:185`). Preference persists under `fleet_portal_lang` — **the same key `/fleet` uses**, so a choice on one board silently changes the other. |

### Pause invariants (keep the rule, not the code)

The pause set at `App.vue:102-109` is behaviour earned by real breakage. A rebuild must keep all
five conditions: never repaint while the board is not ready, while a confirmation is open, while
a sub-form is open, while any per-vehicle action is in flight, or while anything is selected.
And it must keep the replay: an update that arrived during a pause fires once the pause lifts,
rather than being dropped (`App.vue:126-138`).

---

## 6. What is deliberately dropped

| Dropped | Evidence |
|---|---|
| **Two whitelisted endpoints with no caller.** `get_status_meta`, `get_vehicle_timeline`. | `apex/salis/api/fleet_os.py:193` and `:208`. A repo-wide grep across `apex/` and `frontend/` finds the definitions only. |
| **A duplicated language toggle that has drifted.** | `frontend/fleet_os/src/components/LangToggle.vue` is a near-copy of `frontend/frontend_shared/components/LangToggle.vue`, which `/fleet` and `/masar-supervisor` both use. The local copy still uses the retired token names (`--r2`, `--r3`, `--bg3`, `--b1`, `--t3`, `--blue`) and lacks the shared component's `variant` and its `--tap-min` sizing. Two implementations of one control is the defect; the shared one is the survivor. |
| **`reader_errors` handling.** | Server produces it (`fleet_os_board.py:362`), client never reads it (`useFleetBoard.js:20-21`). Either surface it or stop returning it. |
| **Two error strings copied verbatim from the shared table.** `errors.rateLimited`, `errors.sessionExpired`. | `src/i18n.js:63-64` and `:461-462` reproduce, word for word in both languages, what `frontend_shared/sharedMessages.js:8-20` already supplies. `createI18n` falls through to the shared table on a miss (`frontend_shared/i18n.js:28-32`), so the local copies are pure drift risk. Only `errors.loadError` (`:61`, `:459`) is genuinely local. |
| **Dead CSS — whole feature areas no component renders.** All line numbers are `frontend/fleet_os/src/index.css` (926 lines). | A full class sweep against every `.vue`/`.js` in this portal plus `frontend_shared`, after excluding classes built at runtime (`toast-*` from `App.vue:293`; `vs-*` from `FleetCardGrid.vue:29` and `FleetDriverLens.vue:34`; `fp-overlay-*`/`fp-panel-*` from the two `<transition name=…>` at `VehiclePanel.vue:15,18` and `AlertDrawer.vue:11,14`), leaves the blocks below. |
| — a fuel-price editor modal and its price grid | `.fuel-rate-edit` 203-207, `.fuel-modal` 208-217, `.fuel-input-grid` 218, `.fuel-field` 219-226, `.fuel-sar-card` 231-235, `.fsc-lbl` 237, `.fuel-price-row` 238, `.fpr-item` 243-244, `.active-grade` 245-246 |
| — a rental-office card and its edit panel | `.office-card` 566-571, `.oc-body` 573, `.oc-head` 574, `.office-edit-panel` 584 (plus the rest of the `oc-*` set) |
| — a photo / PDF / upload / lightbox subsystem | `.upload-zone` 656-663, `.uz-ico` 663, `.photo-preview` 664-669, `.ph-del` 669, `.pdf-preview` 674-683, `.pdf-del` 679, `.driver-photos` 684, `.lightbox` 689-691, `.lightbox-close` 691 |
| — an email-configuration modal and a folder-status pill | `.email-cfg-modal` 639, `.folder-status` 648, `.fs-ok` 649, `.fs-none` |
| — an iqama-expiry warning widget | `.iqama-warn` 613, `.iqama-warn-count` 617 |
| — a WhatsApp preview and a workshop form | `.wa-preview` 712, `.ws-form` 564 |
| — **classes no component renders, in live families**: `.ti-workshop` 520, `.ti-available` 521, `.ti-event` 522, `.ti-stolen` 594 (only `ti-active` and `ti-stopped` are produced, at `VehiclePanel.vue:304`); `.incident-badge-stolen` 610 (only `-ok` and `-acc` are produced, at `VehiclePanel.vue:271,288`) | as cited |
| — strays | `.status-pills` 42 and 799-805, `.tb-actions` 56, `.sort-row` 159 |
| **Deletion caveat.** | Four of the dead classes also appear inside a shared tap-target rule at `index.css:917-919` (`.fuel-rate-edit, .ph-del, .pdf-del, .lightbox-close`). Removing the blocks means editing that selector list too, or the rule keeps them alive as CSS with no markup. |

---

## Defects found while reading

### Confirmed as briefed — but they live in the **desk** page, not in this SPA

The two named findings are real and reproduce exactly as described, in
`apex/salis/page/operations_control/operations_control.js` (the Salis Operations Control desk
page, `/app/operations-control`), **not** in `frontend/fleet_os/`. Recording the true location so
a rebuild of this portal does not go looking for them here:

1. **`_clear_filters` rebuilds the filter object without one key.** The constructor initialises
   `this.filters = { status, rental_office, project, search, compliance }` (line 123).
   `_clear_filters()` rebuilds it as `{ status, rental_office, project, search }` (line 618) —
   `compliance` is gone. It is set by `_toggle_compliance_risk()` (line 528) and read by the
   summary (line 515), so a compliance filter survives "Clear filters".
2. **…and leaves controls unreset.** The same function never touches `this._incidents_only`
   (read at 508 and 565) or `this.severity_filter` (read at 566 and 695), so the Open Incidents
   chip stays pressed and still filtering after a clear.
3. **`_incidents_only` is read while never initialised.** It appears nowhere in the constructor
   (123-135); its first assignment is `this._incidents_only = !this._incidents_only` at line 533,
   which reads `undefined`. It works only by accident of falsiness.
4. **Two independent un-sequenced fetches both repaint.** `refresh()` fires `_refresh_alerts()`
   (line 279) and `get_fleet` (line 280) with no ordering, and **both** callbacks end in
   `this._render_summary(); this._render();` (292-293 and 317-319). Whichever resolves last wins,
   so a slow response overwrites a newer one.

### The same classes of defect, in **this** portal

5. **The filter reset leaves the sort control unreset — the exact analogue of finding 1.**
   `resetFilters()` (`src/useFleetFilters.js:61-75`) clears every filter key and resets `sortCol`
   and `sortDir`, but **never resets `f.sort`** — and `f.sort` is what the list actually sorts by
   (`useFleetFilters.js:142`). Two consequences: after "Clear filters" the list stays sorted by,
   say, longest-running while the sort control still reads that value and the internal `sortCol`
   says `plate`; and the next click on the plate column header sees `sortCol === "plate"` and
   flips to **descending** instead of starting ascending (`useFleetFilters.js:34`).

6. **Two independent un-sequenced fetches both repaint — the exact analogue of finding 4.**
   `reloadFleet()` (`useFleetBoard.js:28-38`) and `loadAlerts()` (`useAlerts.js:13-23`) each
   assign their result unconditionally, with no request sequence number and no abort. They are
   started from four places — mount, the 30 s poll, the realtime handler, and `visibilitychange`
   (`App.vue:144-150`, `:110-114`, `:127-135`, `:139-143`). Two overlapping `reloadFleet()` calls
   have nothing preventing the older response from landing last and overwriting the newer board.
   `usePoll` guards this with an `inFlight` flag (`frontend_shared/usePoll.js:8-19`) — this
   portal does not use `usePoll` and has no equivalent.

7. **A failed reassign handover leaves the vehicle reassigned.** `submitReassign`
   (`useDriverAssignment.js:76-97`) treats `create_handover` as best-effort: its failure toasts a
   warning and the reassign stands. That may be intended, but it is a two-step write with no
   compensation and nothing on screen records that the handover is missing.

8. **`stop_vehicle` is chained client-side into a second write.** `confirmStop`
   (`useFleetActions.js:50-57`) awaits `stop_vehicle`, then issues `workshop_in` or `recover` as a
   separate request. If the second fails, the vehicle is stopped but not in the state the
   supervisor chose, and the error toast does not say which half succeeded.

9. **The board's sortable columns are not keyboard reachable.** `components/FleetTable.vue:17-26`
   puts `@click` on bare `<th>` elements — no `<button>`, no `tabindex`, no `aria-sort`.

10. **The alerts drawer links to a deprecated record.** `openAlertTarget`
    (`useAlerts.js:45`) opens `/app/operations-alert/<name>` when the alert's vehicle is not on
    the current board. `Operations Alert` is a deprecated DocType; the fallback path sends the
    supervisor to a record type that is on its way out.

11. **`driver_lens` is a capability that gates nothing.** `www/fleet_os.py:53` sets it to the
    role check that already decided whether the page renders at all, so `canDriverLens`
    (`App.vue:98`) is true for every user who can see the board. Either give it a distinct role
    or drop the indirection.
