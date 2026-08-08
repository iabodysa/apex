# /fleet — capability

The page where an ordinary employee who happens to hold a company vehicle checks that vehicle,
looks at his own recent trips, and asks for fuel.

Bundle `fleet_portal`, built from `frontend/fleet`, served by `apex/www/fleet.py` +
`apex/www/fleet.html`, backed by `apex.salis.api.fleet_employee`.

---

## 1. What it does

Three routes, hash history, unknown paths redirect to home
(`frontend/fleet/src/router.js:4-9`).

| Route | The decision or task it serves |
|---|---|
| `#/` home | Is the vehicle I hold in order — plate, category, office, status, odometer, registration expiry — and what are my next two trips? |
| `#/trips` | What have I driven recently: title, date, departure time, distance. |
| `#/fuel` | Ask for fuel: grade, litres, station, a note. Then: what happened to the requests I already sent? |

### Screens that serve nothing — findings

- **The trip rows carry a forward affordance that leads nowhere.** Both on home and on the trips
  list each row ends with a chevron (`src/pages/Home.vue:111`, `src/pages/Trips.vue:62`), but the
  `<li>` has no click handler and there is no per-trip route in the router. There is nothing to
  open. Either give the row a destination in the rebuild, or drop the affordance.
- **The home fuel card is a link and nothing else** (`src/pages/Home.vue:121-132`). It carries a
  heading, a hint and a button to `#/fuel`. It shows no fuel state at all — not the last request,
  not a quota, not a pending count. As a card it is decoration; as navigation it duplicates the
  nav bar.

---

## 2. How it works

Five endpoints, all in `apex/salis/api/fleet_employee.py`. **All five carry
`@frappe.whitelist()`**; `submit_fuel_request` additionally carries `methods=["POST"]`. None is
missing its decorator, and none is `allow_guest`.

Every path is built by **template literal** — `` call(`${API}.get_my_vehicle`) `` with
`API = "apex.salis.api.fleet_employee"` (`src/useEmployee.js:5`). A rebuild grepping for literal
dotted paths finds zero of them.

| Dotted path | Sends | Does with the answer | Called from |
|---|---|---|---|
| `apex.salis.api.fleet_employee.get_my_vehicle` | nothing | Fills the vehicle card, or sets the empty state when `vehicle` is null | `useEmployee.js:33-50` |
| `…get_my_recent_trips` | nothing on the home path; `days=90, limit=100` on the trips page | Two separate stores: the home preview slices the first two, the trips page keeps its own copy | `useEmployee.js:52-54` and `:60-62` |
| `…get_fuel_stations` | nothing | Fills the station picker and preselects the first | `useEmployee.js:64-68` |
| `…submit_fuel_request` (POST) | `vehicle`, `fuel_grade`, `litres`, `station`, `notes` | Clears the note, toasts success or shows the server message inline | `useEmployee.js:82-101` |
| `…get_my_fuel_requests` | `days=90, limit=30` | Renders the history list | `useEmployee.js:56-58` |

Loading model: `useEmployee.js` is a **module-level singleton**. `vehicle`, `trips`, `stations`
and the form live at module scope; the first `useEmployee()` call sets `started = true` and runs
one combined `Promise.all` load (`useEmployee.js:70-80`, `103-120`). Every later consumer reuses
that state. There is **no polling and no realtime** anywhere in this portal.

---

## 3. Who opens it

**Identity model: a logged-in Frappe User, resolved session-only.** The chain is
`frappe.session.user` → `Employee.user_id` → `Salis Driver.employee`, and it explicitly refuses
to read any portal token cookie: `get_driver_for_session_user`
(`apex/salis/utils/__init__.py:28-34`), whose docstring records that a request cookie must not be
able to change a signed-in user's authority.

The gate, from `apex/www/fleet.py`:

- Guests are redirected: `guest_redirect("/fleet")` (line 57).
- **No role is required.** `context.can_view = 1` unconditionally (line 61). Every logged-in user
  may open the page. `FLEET_ROLES` is defined (lines 27-32) and `has_apps_screen_access()` exists
  (line 52) but is deliberately **not wired** — the `/apps` tile carries no `has_permission`, so
  Frappe never calls it. The docstring (lines 36-51) records why: gating the tile would hide "My
  Fleet" from the ordinary employees the page exists to serve.
- The template has no denial branch at all — it always mounts the app (`fleet.html:23-26`),
  because the page turns nobody away.

**Scoped server-side.** The client never supplies a driver or a vehicle id for reads. Each
endpoint resolves the caller to their own `Salis Driver` and filters on it
(`fleet_employee.py:77`, `116`, `274`). A user who is not a driver gets a **friendly empty
result, never a 403** — `{"vehicle": None}` and `[]` — so an office employee simply sees the
empty state.

The one write is the exception and is guarded three ways
(`fleet_employee.py:203-226`): no driver → `PermissionError`; a client-supplied `vehicle` that is
not the caller's bound vehicle → `PermissionError`; the bound vehicle then **overwrites**
whatever was sent (`vehicle = bound`, line 216). "Bound" means `current_vehicle` else an Active
`Vehicle Assignment` (`apex/salis/utils/__init__.py:51-64`) — the same rule the write side of the
driver portal enforces, deliberately kept in one place.

`fleet.py` does **not** call `render_in_arabic()`, unlike `fleet_os.py` and
`masar_supervisor.py`, even though `fleet.html:3` declares `lang="ar" dir="rtl"`. Server-thrown
messages on this page therefore follow the session user's own language for the initial render.

---

## 4. What is required of it

The employee must be able to finish these, on this page:

1. **Confirm the vehicle he is holding is the right one** — plate, model, office, current status,
   odometer, and when the registration (Istimara) expires.
2. **Check his own recent trips** without asking anyone.
3. **Ask for fuel** for that vehicle: which grade, how many litres, which station, and a note if
   the situation needs one.
4. **See what happened to what he asked for** — pending, approved, done, failed, cancelled.
5. **Be told plainly that he holds no vehicle**, rather than being refused entry, when he is an
   office employee who wandered in.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what |
|---|---|---|
| Server-side gating | **Partly, and deliberately so** | Login is required; role is not. Do not add a role gate — the page exists for role-less employees. The real gate is per-endpoint identity resolution. |
| Row scoping | **Yes, and it is the entire security model** | Session → Employee → Salis Driver, session-only, never a cookie. The client sends no identity for reads. On the write, a client-supplied `vehicle` is validated against the binding and then discarded in favour of the bound one. |
| CSRF propagation | **Yes** | `window.csrf_token` (`fleet.html:13`) → frappe-ui sets `X-Frappe-CSRF-Token` (`frappe-ui/src/utils/frappeRequest.js:19`). Only `submit_fuel_request` needs it, but it needs it absolutely. |
| Realtime rooms + teardown | **No — and the bootstrap is dead code** | `fleet.html:15-20` publishes `window.fleet_socket`. Nothing in `frontend/fleet/src/` reads it; there is no `realtime.js` in this portal. Either delete the bootstrap or connect it; do not carry a socket config that opens no socket. |
| URL state | **Route only** | The three routes are hash routes and survive refresh, Back and sharing. **Nothing else is in the URL** — no trip selection, no fuel-history filter, no scroll anchor. Scroll position is restored from history state (`router.js:14-16`). |
| Offline behaviour | **No** | No service worker, no cache, no queued submit. A submit made offline is simply lost with a toast. Contrast `/driver`, which ships a service worker and a cache. Do not copy offline behaviour here unless asked. |
| Language propagation | **Yes, client half only** | Toggle → `<html lang>`/`dir` (`frontend_shared/useDocumentLanguage.js`) → `_lang` on every request (`frontend_shared/call.js:12-16`) → first source in `frappe/translate.py:46-47`. Also drives `document.title` (`src/App.vue:16-22`) and the `ar-SA-u-nu-latn` number/date locale (`Home.vue:15-18`, `App.vue:42-49`). Preference persists under `fleet_portal_lang` — **the same key `fleet_os` uses**, so a language chosen on one board silently changes the other. |

---

## 6. What is deliberately dropped

| Dropped | Evidence |
|---|---|
| **25 of the 31 translation namespaces**, in both languages. | `src/i18n.js` is 915 lines and defines 31 top-level namespaces per language, but this SPA reads only `common`, `emp`, `fuelGrade`, `statusShort`, plus `lang` and `theme` used by the two shared toggles. Dead: `duration`, `status`, `sheet`, `brand`, `alerts`, `topbar`, `sidebar`, `dateInfo`, `chip`, `main`, `lens`, `card`, `table`, `panel`, `driverTab`, `stopForm`, `reassignForm`, `statusTab`, `stolenForm`, `damages`, `accidents`, `logTab`, `confirm`, `toast`, `bulk`. These are the fleet-supervisor board's vocabulary, left behind when `/fleet` became the employee page and the board moved to `/fleet-os`. |
| `.emp-demo` | `src/index.css:56-63`. No markup in this portal carries the class. |
| `window.fleet_socket` | `fleet.html:15-20` — nothing reads it (see the table above). |
| `has_apps_screen_access()` | `apex/www/fleet.py:52` — kept on purpose, never called. Its docstring is the record of *why* the tile is ungated; keep the reasoning, whether or not the function survives. |

---

## 7. /fleet against /driver — what is genuinely distinct

This is the comparison that decides whether the two trips and fuel screens can later become
shared components.

### Identity — different, and the difference is real

| | `/fleet` | `/driver` |
|---|---|---|
| Who the visitor is | a logged-in Frappe User | a token holder who is **not** a Frappe user |
| Gate | `guest_redirect` → login required (`www/fleet.py:57`) | Guest-accessible; no login (`www/driver.py`) |
| How the subject is resolved | `get_driver_for_session_user` — **session only, cookie explicitly ignored** (`salis/utils/__init__.py:28-34`) | `_resolve_driver` → token first, session as fallback (`api/driver_portal/__init__.py:40-57`) |
| Endpoint decorators | `@frappe.whitelist()` | `@frappe.whitelist(allow_guest=True)` + `@rate_limit(...)` |
| Portal kill switch | none | `_require_enabled()` on every endpoint |
| Not-a-driver | friendly empty state | `PermissionError` on the action endpoints |

The endpoint namespaces are therefore **not** interchangeable: `/fleet` calling a driver-portal
endpoint would open a guest-allowed, token-resolvable door to a session user, and `/driver`
calling a fleet endpoint would break every tokened driver. The owner's ruling that the portals
stay separate is supported by the code.

### Trips — the screens are **not** near-duplicates

| | `/fleet` trips | `/driver` trips |
|---|---|---|
| Endpoint | one: `get_my_recent_trips` | two: `my_trips_today` (default) and `my_trips_recent` |
| Today vs recent | no such split — one recency window | a tab that switches endpoint, persisted in `?tab=` |
| Actions | **none — read-only** | start trip, complete trip, boarding scan, manual boarding, manifest finalise |
| Boarding | absent | expected/boarded counts per row, plus a scanner and a manual path |
| Live | none | realtime room + a `wait_request` event, and a 30 s GPS push while a trip is running (`driver/src/pages/Trips.vue:308-342`) |
| Row payload | 6 flat fields, distance derived from the odometer delta server-side (`fleet_employee.py:146-161`) | route/vehicle labels, maps URLs, log state, stop progress, boarding counts (`driver_portal/trips.py:46-49`) |
| Selection / deep link | none | `?trip=<name>` deep link, split detail on desktop, dialog on mobile |

**Verdict: distinct.** `/fleet`'s trips screen is a read-only recency list. `/driver`'s is the
driver's working surface. The only genuinely shared thing is the *row shape* — a status pill, a
title, a date, a duration — which is already a shared concern, not a screen.

### Fuel — overlapping, but each holds something the other does not

| | `/fleet` fuel | `/driver` fuel |
|---|---|---|
| Form fields | grade, litres, station, notes | litres only |
| Station picker | yes — from `get_fuel_stations` (active `Fuel Platform`) | no; `fuel_platform` accepted by the endpoint but never sent from the SPA |
| Grade and notes | sent, and — because `Fuel Request` has no field for them — preserved as a **timeline note** on the created request (`fleet_employee.py:244-250`) | not collected, not stored |
| Quota shown | **no** | yes: remaining / consumed / monthly allowance, plus the approval-threshold note (`driver_portal/fuel.py:89-143`) |
| Quota **enforced** | yes — the request is bound to the month's `Fuel Quota` and `_guard_quota_allowance()` runs before insert (`fleet_employee.py:227-241`) | identically (`driver_portal/fuel.py:74-83`) |
| After a successful submit | toast only; the history list is **not** refreshed | history and quota both reload (`driver/src/pages/Fuel.vue:117-123`) |
| History row | date, litres, station, vehicle plate, status | date, litres, station label, status |

**Verdict: the fuel screens are the only genuine convergence candidate, and they are not
convergent yet.** The enforcement is already identical and already shared through
`salis.utils.period_quota` — that part must not be duplicated again. What differs is the *form*:
`/fleet` collects three fields the driver portal does not, and `/driver` shows a quota bar
`/fleet` does not. Both differences are product choices, not identity consequences.

### The precise answer

- **What differs only because the identity differs:** nothing on the screens themselves. The
  identity difference is confined to the resolver, the whitelist decorator, the rate limit, the
  kill switch, and the not-a-driver response.
- **What differs for real product reasons:** the whole of trips (actions, boarding, live
  position, today/recent split, deep links), and, within fuel, the extra form fields on one side
  and the quota bar on the other.
- **How much of `/fleet` is a subset of `/driver`:** roughly **one screen of three**. Home is
  unique to `/fleet` (no `/driver` screen shows vehicle + trip preview + fuel entry together;
  `/driver` splits that across Home, Vehicle and Profile). Trips is a strict, much smaller subset
  in *data* but shares no behaviour. Fuel is a partial overlap in both directions — neither is a
  subset of the other.
- **Therefore:** a shared *fuel request form* component is defensible if the quota bar becomes
  optional and the three extra fields become optional. A shared *trips screen* is not — the two
  screens serve different jobs. Do not merge on the strength of the route names.

---

## Defects found while reading

1. **The fuel history does not refresh after a successful submit.** `src/pages/Fuel.vue:35-46`
   toasts and returns; `loadHistory()` runs only `onMounted` (line 33). The request the employee
   just sent does not appear in "my requests" until he reloads the page. `/driver` gets this
   right (`driver/src/pages/Fuel.vue:117-123`).

2. **Two independent, silently different trip windows.** The home preview calls
   `get_my_recent_trips` with **no arguments**, taking the server defaults of 30 days / 20 rows
   (`useEmployee.js:53`, `fleet_employee.py:105`). The trips page calls it with `days=90,
   limit=100` (`useEmployee.js:61`). The same list therefore shows different trips depending on
   which screen you are on, with nothing on screen saying so. Note also that the server does not
   clamp `days`/`limit` here, unlike the driver portal which bounds both
   (`driver_portal/trips.py:26-31`).

3. **A forward chevron on rows that do not open.** `Home.vue:111` and `Trips.vue:62` — see §1.

4. **`loadError` is a single flag for three parallel loads.** `useEmployee.js:70-80` runs
   vehicle, trips and stations in one `Promise.all` and sets one boolean. Each consumer then
   re-qualifies it differently — `loadError && vehicle.empty`, `loadError && !trips.length`,
   `loadError && !stations.length` (`Home.vue:44`, `Home.vue:88`, `Fuel.vue:53`). If one of the
   three fails the other two report an error they did not have.

5. **`submit_fuel_request` writes with `ignore_permissions=True`** (`fleet_employee.py:242`).
   Correct here — the endpoint is the authorization boundary and has already proved the binding —
   but a rebuild must keep the three guards above it, or this line becomes the hole.

6. **The language key is shared with another portal.** `fleet_portal_lang` is the storage key in
   both `frontend/fleet/src/i18n.js:4` and `frontend/fleet_os/src/i18n.js:4`.
