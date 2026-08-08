# /housing — capability

A logged-in housing worker records a physical count of a building's Housing Inventory, and clears or receives a Facility Asset Delivery through its three exit checkpoints.

---

## 1. What it does

Two screens, reached from a persistent two-tab nav (`src/App.vue:79-82`). The default route `/` redirects to `/count` (`src/router.js:7`).

| Screen | Route | The decision or task it serves |
|---|---|---|
| Building choice | `#/count` while no building is chosen | "Which building am I counting today?" Rendered by `@shared/components/BuildingPicker.vue`, gated at `src/pages/Count.vue:3`. Auto-selects when the user can read exactly one building (`BuildingPicker.vue:58-63`). |
| Inventory count | `#/count`, `#/count/:item` | "Is what the record says is in this room actually in this room?" Lines grouped by room (`Count.vue:215-229`); per line the worker sets counted quantity, condition and a note (`Count.vue:285-293`); one submit posts every touched line. |
| Count filter | `#/count?filter=needs` | "Show me only what has never been counted or is off by a quantity" (`Count.vue:189-197`, predicate at `Count.vue:210-213`). |
| Delivery queue | `#/delivery`, `#/delivery/:name` | "Which assets in transit are stuck at a checkpoint?" and, for one of them, "clear my checkpoint" or "confirm the asset arrived". |

No screen is decorative. Both tabs carry a real write.

**A screen that serves nothing:** none — but the header progress bar counts *edited* lines, not *counted* lines. `countProgress.done` is `Object.keys(touched).length` (`Count.vue:242-250`) rendered against the string "{done} of {total} counted". A building whose every item was counted last week reads 0 of N until the worker retypes them. The bar answers "how much have I typed this session", which is not the question its label asks.

---

## 2. How it works

Every endpoint the portal calls, in call order.

| Dotted path | Verb / caller | Sends | Does with the answer | Whitelisted |
|---|---|---|---|---|
| `frappe.client.get_list` (doctype `Building`) | GET · `BuildingPicker.vue:52-67` via `createListResource` | `fields:[name,building_name]`, `orderBy:"building_name asc"`, `pageLength:99999` | Renders the choice list; emits `select` immediately if exactly one row came back | yes — `frappe/client.py:27` |
| `apex.habitat.api.housing_count.get_inventory_for_building` | GET · `Count.vue:166-169` | `{building}` only | `data.items` → the grouped line list; `data.conditions` → the condition picker options (server-driven from DocMeta, `housing_count.py:61-69`) | yes — `housing_count.py:72` |
| `apex.habitat.api.housing_count.submit_counts` | POST · `Count.vue:317-320` | `{building, lines: JSON.stringify([{name, counted_quantity, condition, notes}])}` | Reads `saved` / `failed`; raises a success or a partial-success toast; clears the staged set; reloads the inventory | yes, POST-only — `housing_count.py:126` |
| `frappe.client.get_list` (doctype `Facility Asset Delivery`) | GET · `Delivery.vue:220-239` | `filters:[["status","in",["Pending Exits","Released"]]]`, 8 fields incl. the three exit flags, `order_by:"creation asc"`, `limit_page_length:50` | The delivery list and each row's checkpoint state | yes |
| `frappe.client.get_count` (same doctype/filters) | GET · `Delivery.vue:241-245` | same filters | The true total, shown beside the capped list of 50 | yes — `frappe/client.py:81` |
| `apex.habitat.api.facility_asset_delivery.pass_exit_1` / `_2` / `_3` | POST · `Delivery.vue:304` via `@shared/call.js` | `{delivery}` | On success: toast, reload both delivery resources. On failure: the message is shown inline | yes, POST-only — `facility_asset_delivery.py:124,130,136` |
| `apex.habitat.api.facility_asset_delivery.confirm_receipt` | POST · `Delivery.vue:322-325` | `{delivery, code}` (6 digits, `Delivery.vue:318`) | On success: toast, close the detail route, reload | yes, POST-only — `facility_asset_delivery.py:143` |

All seven are `@frappe.whitelist()`. Nothing the portal calls is un-whitelisted.

**Which exit the button offers** is decided client-side by `src/gates.js:12-15` — the first of `exit1_security_cleared`, `exit2_logistics_cleared`, `exit3_receiving_cleared` that is falsy. The server re-derives the same order and refuses out of order (`facility_asset_delivery.py:95-99`).

**Never called by this portal:** `apex.habitat.api.facility_asset_delivery.regenerate_code` (`facility_asset_delivery.py:222`) — see §6.

---

## 3. Who opens it

Login required. `apex/www/housing.py:55` calls `guest_redirect("/housing")`, which for `frappe.session.user == "Guest"` sets `redirect_location = "/login?redirect-to=/housing"` and raises `frappe.Redirect` (`apex/apex_core/utils/portal_bootstrap.py:45-47`). A guest never reaches the page and never receives a CSRF token.

The role set, quoted from `apex/www/housing.py:37-42`:

```python
HOUSING_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Procurement Supervisor",
}
```

`context.has_housing_role = bool(HOUSING_ROLES & set(frappe.get_roles()))` (`housing.py:59`). A logged-in user without one of the four gets the shared refusal include (`housing.html:26-30` → `apex/templates/includes/portal_denied.html`) — a page, not a 403 — and the SPA bundle and the CSRF token are never emitted (`housing.html:11-20, 23-25`).

`has_apps_screen_access()` (`housing.py:45-50`) controls **only** the visibility of the `apex-housing` tile on Frappe's `/apps` selector; it is wired as that tile's `has_permission` in `apex/hooks.py:61-67`. It runs the identical `HOUSING_ROLES` test, so the tile never advertises a page the user would be turned away from. It gates nothing else — a user who knows the URL is still stopped by `get_context`.

### Role → capability (the map the merged portal should gate from)

Page admission is the union above; what a role can actually *do* is the DocPerm behind each call.

| Role | Opens `/housing` | Building list | Count (read / write Housing Inventory) | Delivery list | Exit 1 | Exit 2 | Exit 3 | Confirm receipt |
|---|---|---|---|---|---|---|---|---|
| System Manager | yes | yes | read+write | yes | yes (override, `facility_asset_delivery.py:70-71`) | yes | yes | **no**, unless also the named `receiving_supervisor` or also holding Accommodation Manager — the receipt gate has no System Manager override (`:162-166`) |
| Accommodation Manager | yes | yes | read+write | yes | no | **yes** | no | yes (`ELEVATED_ROLE = "Accommodation Manager"`, `apex/habitat/utils/otp_policy.py:17`) |
| Resident Supervisor | yes | read only | read+write | yes (read+write on FAD) | **yes** | no | no | only if named `receiving_supervisor` |
| Procurement Supervisor | yes | **no read on Building** | **no permission at all** | yes | no | no | **yes** | only if named `receiving_supervisor` |

Sources: DocPerms in `apex/habitat/doctype/{housing_inventory,building,room,facility_asset_delivery}/*.json`; exit roles in `facility_asset_delivery.py:51-55`; the receipt gate in `facility_asset_delivery.py:155-166`. (The OTP fields on Facility Asset Delivery sit at permlevel 1, readable only by System Manager / Procurement Supervisor / Accommodation Manager; every field the portal requests is permlevel 0, so a Resident Supervisor can read the exit flags.)

Two consequences a rebuild must design for, not inherit:
- **Procurement Supervisor lands on a screen it cannot use.** The default route is the count (`router.js:7`), the count opens with the building picker, and Procurement Supervisor has no `read` on `Building` — the picker resolves to its empty state. The merged portal must derive the landing section from the role, not from a constant.
- **Row scoping is server-side and silent.** `Building`, `Room`, `Housing Inventory` and `Facility Asset Delivery` all carry `apex.habitat.permissions.building_scoped_has_permission` / `..._query` (`apex/hooks.py:322,353,355,362,363,387`). A scoped supervisor simply sees a shorter list; nothing in the portal says "scoped". Keep it that way — but keep the scoping.

---

## 4. What is required of it

*Two jobs, in the words of the person doing them.*

**The count.** You walk into a building with a phone. You pick the building. You get every recorded item, grouped by the room it belongs to. For each one you look at it, type how many are actually there, say what condition it is in, and add a note if something needs saying. When you have done the ones you came to do, you press submit once. The system tells you how many were saved, works out the difference against what it expected, and stamps the date it was counted. If one item fails to save, the rest still save and you are told which one failed.

**The delivery.** An asset is being moved between buildings and cannot move until three people sign it out in order: the gate, then dispatch, then receiving. You open the list, find the one waiting on you, read where it is coming from and going to, see which of the three checkpoints are done, and clear yours. You cannot clear someone else's and you cannot clear yours twice. When all three are done the asset is released, and whoever is standing at the destination types the six-digit code that came with it to confirm it arrived — which is the moment the asset actually changes building. The person who sent it cannot be the person who confirms it arrived.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what it is |
|---|---|---|
| Server-side role gating | **Yes** | `HOUSING_ROLES` in `housing.py:37-42`, tested in `get_context` (`:59`) and again for the `/apps` tile (`:45-50`). Every write re-checks: `frappe.has_permission("Housing Inventory","write",throw=True)` (`housing_count.py:157`) and `frappe.has_permission(DELIVERY_DOCTYPE,"write",doc=doc,throw=True)` (`facility_asset_delivery.py:84,153`). The page gate is a courtesy; the API gate is the security. |
| Row scoping | **Yes** | `permission_query_conditions` + `has_permission` on Building, Room, Housing Inventory, Facility Asset Delivery (`apex/hooks.py:322,353,355,362`, with the matching `has_permission` entries from `:382`). `housing_count.py` uses **no** `ignore_permissions` anywhere; `submit_counts` additionally re-checks `doc.building != building` per line and throws `frappe.PermissionError` (`:190-194`), so an out-of-scope item id cannot be smuggled in under an in-scope building. |
| CSRF propagation | **Yes** | `window.csrf_token` is emitted by the Jinja shell **only inside the role branch** (`housing.html:14-19`). frappe-ui attaches it as `X-Frappe-CSRF-Token` on every request (`node_modules/frappe-ui/src/utils/frappeRequest.js:19-20`), which covers both `createResource` and the raw `call()` in `frontend_shared/call.js:22-26`. `context.no_cache = 1` (`housing.py:57`) keeps the token from being cached across users. |
| Realtime rooms and teardown | **No** | The housing surface has no socket. `housing.py` emits no `socketio_port` / `site_name` / `async_enabled`, and nothing under `frontend/housing/` imports `@shared/realtime.js`. The delivery list is refreshed only by the user's own action (`Delivery.vue:254-257`). A rebuild that adds live push here is adding a new capability, not restoring one. |
| Offline drafts and queues | **Yes — and it is thin. Read this one carefully.** | The **only** thing persisted is the chosen building: `localStorage["housing_portal_building"] = {name,label}` (`session.js:4,24-31`). **A half-entered count does not survive a reload.** `staged` and `touched` are component-local `reactive({})` in `Count.vue:163-164` with no write to storage anywhere in the portal. Reload `/housing#/count` mid-count and every typed quantity, condition and note is gone; the building is remembered, so the worker is dropped back onto a full, blank list with no sign that anything was lost. Worse, it is not only reload: `Count.vue` is mounted by a plain `<router-view />` with no `KeepAlive` (`App.vue:42`), so **tapping the Delivery tab and coming back also discards the staged counts.** There is no offline queue and no service worker — `frontend/housing/vite.config.js:4` does not pass `serviceWorkers`, so `stampServiceWorkers` (`frontend_shared/vite.base.js:11-31`) never runs for this portal. Compare `/safety`, which *does* persist its drafts (`makeCache("apex_safety_draft_")`). The merged portal must pick one behaviour; the counting job is the one that most needs the draft. |
| Photo / evidence capture | **No** | Nothing in the count or delivery flow uploads a file. The shared contract exists (`frontend_shared/photoFile.js`, consumed by `frontend/driver/src/upload.js`) and is simply unused here. |
| Routes and deep links | **Yes** | Hash history (`router.js:15`), so the query string lives after the `#`. Bookmarkable: `/housing`, `/housing#/` (→ `#/count`), `/housing#/count`, `/housing#/count/<Housing Inventory name>`, `/housing#/count?filter=needs`, `/housing#/delivery`, `/housing#/delivery/<Facility Asset Delivery name>`. Names are `encodeURIComponent`-ed on the way in (`Count.vue:183`, `Delivery.vue:267`). **Legacy `/housing-count`:** a live route that must keep working. `apex/www/housing_count.py:12-15` sets `redirect_location = "/housing#/count"` and raises `frappe.Redirect`. It only resolves because the sibling marker `apex/www/housing-count.html` exists — a template-less www controller is never imported (the controller's own docstring, `housing_count.py:5-8`); that marker also carries a `<meta http-equiv="refresh">` to the same target (`housing-count.html:7`) as a belt-and-braces fallback. Delete the marker and the legacy bookmark 404s. Also live: the `/apps` tile route `/housing` (`apex/hooks.py:65`). |
| Language propagation | **Yes, both directions** | Client: the portal's own i18n owns the document (`useDocumentLanguage(lang, dir)`, `App.vue:105`), storing the choice in `localStorage["housing_portal_lang"]` (`src/i18n.js:4`). Server: `frontend_shared/call.js:12-16` reads `document.documentElement.lang` and appends `_lang` to **every** request; Frappe reads `frappe.form_dict._lang` as the highest-priority language source (`frappe/translate.py:46-47`, applied per request at `frappe/auth.py:101`). That is what makes a server-thrown message such as "Item {0} does not belong to this building." come back in the language the worker is reading. Do not drop `_lang` as "an unused parameter" — it is a framework convention, not ours. |

---

## 6. What is deliberately dropped

Each with the search that earns it.

| Dropped | Evidence |
|---|---|
| The `room` parameter of `get_inventory_for_building` | The endpoint accepts `get_inventory_for_building(building, room=None)` and filters on it (`housing_count.py:73,96-97`). The sole caller sends `{building: building.value}` and nothing else (`Count.vue:168`). Repo-wide grep for `get_inventory_for_building` returns one frontend hit. Room is a grouping in the UI, never a server filter. |
| `apex.habitat.api.facility_asset_delivery.regenerate_code` | Whitelisted at `facility_asset_delivery.py:222`. Grep for `regenerate_code` across `apex/` + `frontend/` returns exactly two hits: the definition, and `apex/habitat/doctype/facility_asset_delivery/facility_asset_delivery.js:95` — the **desk form**, not the portal. |
| The on-site code returned by exit 3 | `_pass_exit` sets `frappe.response["delivery_otp"] = code` when `n == 3` (`facility_asset_delivery.py:115`). Grep for `delivery_otp` across `apex/` + `frontend/` returns **only the two writers** (`facility_asset_delivery.py:115` and `.../facility_asset_delivery.py:99`) and no reader. `Delivery.vue:304` awaits `call(...)`, which resolves to `response.message` — a sibling response key is unreachable from there. The code is minted, given a 10-minute expiry (`custody_handover.py:125`), and discarded. |
| Local `src/components/LoadError.vue` | Duplicates `frontend_shared/components/LoadError.vue`; `diff` shows only class names and icon plumbing. Housing imports the local copy (`Count.vue:151`, `Delivery.vue:199`) and never the shared one. |
| Message keys with no consumer (en **and** ar) | `greeting.morning|afternoon|evening|eyebrow`, `list.title`, `list.subtitle`, `list.empty`, `list.countedToday`, `list.lastCount`, `list.neverCounted`, `submit.hint`, `success.title|subtitle|results|shortage|surplus|balanced|done|another`, `nav.sections`, `delivery.title|eyebrow|subtitle|waiting|route`, `common.loading|error|submit|confirm|back|change|close`, `errors.noBuilding`. Grep across `frontend/housing/src` and `frontend/frontend_shared` (excluding `i18n.js` itself) returns no hit for any of them. `success.saved` / `success.partial` **are** used (`Count.vue:329`); `nav.count` / `nav.delivery` are used dynamically via `t(tab.labelKey)` (`App.vue:80-81,89`) — keep those. The dead `success.*` and `greeting.*` blocks are the residue of a success screen and a greeting header this portal no longer has; `/safety` still has both (`safety/src/App.vue:29,62,71,87,356-358`). |
| Four strings duplicated from the shared fallback | `common.error`, `errors.rateLimited`, `errors.sessionExpired`, `errors.loadError` are byte-identical in `src/i18n.js` and `frontend_shared/sharedMessages.js:3-24`, in both languages. `createI18n` already falls through to the shared pool (`frontend_shared/i18n.js:28-32`), so the local copies are inert. |

**Not dropped, and not this portal's to delete:** the desk pages `apex/habitat/page/{front_desk,arrivals_desk,transfer_board,custody_kiosk,safety_map}` stay. Only one has a bearing here — none of them touch Facility Asset Delivery (grep for `Facility Asset Delivery` under `apex/habitat/page/` returns nothing). **The reference implementation for the delivery job is the DocType form JS `apex/habitat/doctype/facility_asset_delivery/facility_asset_delivery.js`**, not a Page: it is the only surface that can surrender the on-site code (`:88-112`, via `regenerate_code`). `custody_kiosk` handles `Custody Article`, a different item master from `Housing Inventory` — it is not an overlap with the count.

---

## Defects found while reading

1. **The header building change no longer strands counts — keep it that way.** `Count.vue:269-272` watches `building` and calls `clearStaged()`; its comment (`:264-268`) records why: there are two ways to change the building — this page's control (`Count.vue:259-262`) and the header's (`App.vue:100-103`) — and the header's used to leave the previous building's staged counts alive, so the progress bar reported them against the new building and a submit posted the **old item names under the new building name**. The fix works because the watcher lives with the data, not on either button. A rebuild that puts the clear inside the click handlers will reintroduce the bug the moment a third way to change the building appears. Files: `frontend/housing/src/pages/Count.vue:259-277`, `frontend/housing/src/App.vue:100-103`, `frontend/housing/src/session.js:38-42`.
2. **Staged counts are lost on reload and on tab switch, silently.** See §5. `Count.vue:163-164` + no `KeepAlive` at `App.vue:42`.
3. **The delivery list claims to be personal and is not.** The filter is `status in ["Pending Exits","Released"]` for everything the caller can read (`Delivery.vue:218`), but it is labelled "Awaiting your action" / "{n} awaiting you" (`i18n.js:130,158`). A Resident Supervisor is therefore shown deliveries whose next checkpoint is exit 2 or exit 3, offered a button reading "Clear Logistics / Dispatch" (`Delivery.vue:73`), and refused by the server with a `PermissionError` after tapping it (`facility_asset_delivery.py:72-75`). The queue should be filtered by the caller's exit role.
4. **Only the oldest 50 deliveries are reachable.** `limit_page_length: 50` with `order_by: "creation asc"` (`Delivery.vue:236-237`) and no paging control; the true total is fetched separately and merely displayed (`Delivery.vue:241-252`). Delivery 51 cannot be opened from this portal at all.
5. **A completed delivery cannot be completed from this portal.** Exit 3 mints the on-site code into a response key the portal never reads (§6), and the portal exposes no `regenerate_code`. The receipt dialog's own hint says the code "is on the delivery note that came with the asset" (`i18n.js:167`) — nothing in the app writes that note. In practice someone must open the Desk form to get the code, which means the portal's delivery flow is not self-sufficient.
6. **The progress bar measures typing, not counting.** §1.
7. **The shipped shell locks zoom; the dev shell deliberately does not.** `apex/www/housing.html:6` sets `maximum-scale=1`, while the dev entry `frontend/housing/index.html` carries an explicit comment that a supervisor counting in a store room must be able to pinch to 200% and omits the lock. The production page contradicts the stated intent and fails WCAG 1.4.4.
8. **The refusal page can render the wrong language for its own box.** `apex/www/safety.py:50` calls `render_in_arabic()` so its `lang="ar" dir="rtl"` shell agrees with the strings `_()` produces; `apex/www/housing.py` makes no such call while `housing.html:3` declares `lang="en"`. On a site whose users default to Arabic, `portal_denied.html` paints Arabic sentences inside an LTR, English-declared box — the mirror image of the bug `apex/apex_core/utils/portal_language.py:5-9` was written to fix.
9. **A docstring cites a guard that is not in this tree.** `apex/www/housing_count.py:8` points at `www/test_www_controller_has_template.py` to explain why the `housing-count.html` marker may not be deleted. That file does not exist in the repo. The constraint is real; the citation is dangling, and a rebuilder who checks it will conclude the marker is safe to remove.
