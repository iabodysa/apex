# Salis Driver (`/driver`) — capability record

The Driver portal is the phone app a bus and vehicle driver opens from his own private link to run his working day: clock in, start his trip, board his passengers, close the manifest, ask for fuel, and raise a problem.

---

## 1. What it does

Nine screens behind a hash router (`frontend/driver/src/router.js:4-19`). Three are in the bottom bar (`frontend/driver/src/App.vue:133-137`); the other six are reached from Home cards and the Profile list.

| Route | Screen | The decision or task it serves |
|---|---|---|
| `#/` | Home | "What is the next thing I must do?" One dock button computed server-state-first: not checked in → Attendance; a trip exists → open or resume it; otherwise → check out; checked out → done (`src/today.js:28-40`). Around it: today's shift card, blocking alerts (licence expired/expiring, no vehicle bound, open clearance — `pages/Home.vue:101-140`), the next trip, and system notifications. |
| `#/attendance` | Attendance | "Clock in / clock out, with proof." One check-in and one check-out per day, each optionally carrying a camera photo, plus this month's attendance history with status pills. |
| `#/trips` | Trips | "Run my trips." Two tabs — today (live, actionable) and recent (read-only, 30 days). A dock button that walks the trip through start → board → complete (`src/trips.js:26-36`). Selecting a trip opens a detail pane (side panel on desktop, dialog on phone). This screen owns the socket, the boarding overlays, and GPS position pushing. |
| `#/route`, `#/route/:trip` | Route | Two different things behind one component. Without a param: all of today's worker-line routes with their stops, map links and worker manifest with tel: links. With a param: one trip's stops as a tickable stepper (only after the trip is started), plus its workers. |
| `#/fuel` | Fuel | "Ask for fuel." Monthly quota with consumed / remaining, the approval threshold note, a litres field, and request history with status pills. |
| `#/tickets` | Tickets | "Raise a problem and follow it." Category/priority/subject/description with an optional camera photo; the list of the driver's tickets; and a detail view with SLA dates, a paginated conversation, and a reply box. |
| `#/profile` | Profile | "My record, my documents, my exit." Driver identity, licence with expiry countdown and a one-tap renewal request, Iqama/passport, exit-clearance status with a certificate download when issued, language switch, and Web Push opt-in. |
| `#/vehicle` | Vehicle | "Is my vehicle legal, and something is wrong with it." Plate, category, odometer, fuel grade, compliance documents (registration / insurance / periodic inspection) with expiry state, and a free-text problem report. |
| unknown hash | — | **Nothing.** The router has no catch-all (`router.js:4-19`). An old or mistyped deep link paints the shell with an empty body. |

**Finding on unreachable capability.** The stop stepper on `#/route/:trip` marks a stop *done*. There is no control anywhere in this portal for marking *arrival* at a stop, even though `apex.salis.api.driver_portal.mark_arrived` exists, publishes `boarding_arrived`, and is the sole writer of the flag the worker's Masar app reads to show "your driver has arrived" (`apex/salis/api/driver_portal/__init__.py:385-442`). `grep -rn "mark_arrived"` across the whole repo excluding `node_modules`/`__pycache__` finds the definition, one docstring mention in `boarding_window.py:24`, and out-of-tree tests under `.claude/tests/` — no caller in any frontend. The arrival half of the boarding window is server-complete and UI-absent.

---

## 2. How it works

All calls go through `frappe-ui`'s `createResource` (or the thin `@shared/call.js` wrapper in `push.js`). The shared fetcher appends the current `<html lang>` as `_lang` on every request (`frontend_shared/call.js:12-20`), which is Frappe's precedence-1 language source (`frappe/translate.py:46`).

`configureApi()` runs before the plugin, and the plugin is installed with `socketio: false` (`frontend_shared/bootstrap.js:15-23`) — deliberately, because this portal opens and tears down its **own** socket with its own room (see §5).

All 38 endpoints below are `@frappe.whitelist(allow_guest=True)` and all are throttled. **No exceptions found.** One does it differently and the difference matters: `apex.salis.api.boarding.scan_boarding_pass` carries no `@rate_limit` decorator because it throttles *inside* the function, after resolving authority (`apex/salis/api/boarding.py:408-413`) — it authorizes the actor first, charges a rejected caller against a per-IP window, and charges an authorized caller against their server-resolved driver-or-staff identity. A rebuild must not "tidy" that into the decorator; the decorator cannot see the actor.

### Shell and Home

| Dotted path | Called from | Sends | What the client does | Limit |
|---|---|---|---|---|
| `apex.salis.api.driver_portal.get_driver_context` | `App.vue:107-111` | — | The gate. Renders the app only when `enabled && linked && driver` (`App.vue:113-115`). Otherwise `Unlinked.vue` renders a staff panel with permission-filtered desk links, or a generic "not linked" explainer. Never raises. | 120/60s |
| `apex.salis.api.driver_portal.get_my_today` | `src/today.js:9-13` | — | A **module-level singleton resource** — created once, shared by Home and reloaded by Trips after every start/complete. Feeds the shift card, alerts, next trip and the dock step. | 120/60s |
| `apex.salis.api.driver_portal.get_my_notifications` | `pages/Home.vue:70-73` | — | Native `Notification Log` rows for the driver's linked user, filtered to rows whose referenced document the driver actually owns. Display only — there is no mark-as-read. | 120/60s |

### Trips and execution

| Dotted path | Called from | Sends | What the client does | Limit |
|---|---|---|---|---|
| `apex.salis.api.driver_portal.my_trips_today` | `pages/Trips.vue:153-156` | — | The live list. Reloaded on socket `driver_trip_update`, after start/complete, and after any boarding action. | 120/60s |
| `apex.salis.api.driver_portal.my_trips_recent` | `pages/Trips.vue:157-159` | — | Lazy — fetched only when the "recent" tab is first opened (`Trips.vue:172-178`). | 120/60s |
| `apex.salis.api.driver_portal.start_my_trip` | `pages/Trips.vue:244-247` | `dispatch_trip` | POST. Toast, reload today, **and start GPS tracking for that trip**. | 10/60s |
| `apex.salis.api.driver_portal.complete_my_trip` | `pages/Trips.vue:248-251` | `dispatch_trip` | POST. Toast, reload today, stop GPS tracking if it was this trip. | 30/60s |
| `apex.salis.api.driver_portal.push_driver_position` | `pages/Trips.vue:309-312` | `dispatch_trip`, `lat`, `lng` | POST every 30 s from `navigator.geolocation.getCurrentPosition` while a started trip is tracked. Errors are swallowed by design (`onError: () => {}`). | 30/60s |
| `apex.salis.api.driver_portal.my_worker_route_today` | `pages/Route.vue:253-255` | — | All of today's worker-line routes. Server wrapper over `masar.get_my_worker_route_today`. | 120/60s |
| `apex.salis.api.driver_portal.my_trip_route` | `pages/Route.vue:257-260` | `dispatch_trip` | One trip's stops + workers. | 120/60s |
| `apex.salis.api.driver_portal.mark_stop_progress` | `pages/Route.vue:281-284` | `dispatch_trip`, `route_stop`, `done`, `sequence`, `stop_name` | POST. Optimistic toggle, then the returned `stop_progress` map is replayed over every stop; on throw the toggle is reverted (`Route.vue:286-310`). | 30/60s |

### Boarding

| Dotted path | Called from | Sends | What the client does | Limit |
|---|---|---|---|---|
| `apex.salis.api.boarding_flow.get_trip_boarding` | `components/BoardingManifest.vue:99-104` | `dispatch_trip` | The manifest panel's read. Explicitly the **pure** read — opening the panel must not burn a reminder (`boarding_flow.py:357-365`). Reloaded on every realtime boarding event. | 120/60s |
| `apex.salis.api.boarding.scan_boarding_pass` | `components/BoardingScanner.vue:66-68` | `pass_token`, optional `stop_name`, `accommodation_building` | POST. The QR result. Five outcomes render distinct result cards: `Valid`, `Duplicate`, `Wrong Trip`, `Expired`, `Invalid Token` (`BoardingScanner.vue:70-76`). Only `Valid` emits `boarded`. A `Wrong Trip` answer additionally carries the correction the misboarded worker's own app will show. | in-body, actor-scoped |
| `apex.salis.api.driver_portal.manual_boarding_sheet` | `components/ManualBoarding.vue:75-79` | `dispatch_trip` | The tick-list of expected workers, with already-boarded rows locked. | 120/60s |
| `apex.salis.api.driver_portal.manual_board_workers` | `components/ManualBoarding.vue:82-85` | `dispatch_trip`, `workers` (JSON array) | POST. Boards the ticked set in one call, toasts the count, reloads the sheet. | 10/60s |
| `apex.salis.api.boarding_flow.driver_mark_not_boarded` | `components/BoardingManifest.vue:136-139` | `dispatch_trip`, `employee` | POST. The override — undoes a worker's self-confirm. The only per-worker driver intervention in the flow. | 30/60s |
| `apex.salis.api.boarding_flow.notify_remaining_passengers` | `components/BoardingManifest.vue:153-156` | `dispatch_trip` | POST. Nudges every still-Pending worker; the button's label and the reminder counter change once the grace window has elapsed (`BoardingManifest.vue:57-66`). | 30/60s |
| `apex.salis.api.boarding_flow.depart_and_finalize` | `components/BoardingManifest.vue:170-173` | `dispatch_trip` | POST. Closes the manifest; still-Pending workers who exhausted their reminders become Absent. Returns `{boarded, absent, pending}` which is rendered as a departure summary. | 30/60s |

### Attendance, fuel, support, profile, vehicle, push

| Dotted path | Called from | Sends | What the client does | Limit |
|---|---|---|---|---|
| `apex.salis.api.driver_portal.get_today_attendance` | `pages/Attendance.vue:178-183` | — | Today's state → the whole button-enable logic. | 120/60s |
| `apex.salis.api.driver_portal.driver_check_in` | `pages/Attendance.vue:185-189` | `photo`, `photo_filename` | POST. Applies the returned state, clears the photo, toasts, reloads history. | 10/60s |
| `apex.salis.api.driver_portal.driver_check_out` | `pages/Attendance.vue:190-194` | `photo`, `photo_filename` | POST. Same. | 10/60s |
| `apex.salis.api.driver_portal.my_attendance` | `pages/Attendance.vue:251-254` | — | `{rows}` → history list. | 120/60s |
| `apex.salis.api.driver_portal.my_fuel_quota` | `pages/Fuel.vue:106-109` | — | Rendered only when `has_quota`; drives the used-percentage bar and the approval-threshold note. | 120/60s |
| `apex.salis.api.driver_portal.my_fuel_requests` | `pages/Fuel.vue:110-113` | — | History with status pills. | 120/60s |
| `apex.salis.api.driver_portal.submit_fuel_request` | `pages/Fuel.vue:115-124` | `litres` | POST. Toasts the created name, clears the field, reloads both history and quota. | 10/60s |
| `apex.salis.api.driver_portal.my_support_tickets` | `pages/Tickets.vue:190-193` | — | The list. | 120/60s |
| `apex.salis.api.driver_portal.raise_support_ticket` | `pages/Tickets.vue:194-206` | `category`, `priority`, `subject`, `description`, `photo`, `photo_filename` | POST. Clears the form and reloads the list. | 10/60s |
| `apex.salis.api.driver_portal.get_ticket` | `pages/Tickets.vue:257-263` | `name`, `communication_offset`, `communication_limit` (20) | Two separate resources over the same endpoint — one for the first page, one for "load more" — so a slow page-2 cannot overwrite a freshly opened ticket. | 120/60s |
| `apex.salis.api.driver_portal.reply_to_ticket` | `pages/Tickets.vue:342-344` | `name`, `message` | POST. On success bumps the generation, clears state and reloads the detail from page 0. | 10/60s |
| `apex.salis.api.driver_portal.get_driver_profile` | `pages/Profile.vue:248-251` | — | Identity, licence, documents. Licence countdown is computed client-side from `license_expiry` (`Profile.vue:284-291`). | 120/60s |
| `apex.salis.api.driver_portal.my_clearance` | `pages/Profile.vue:253-256` | — | Rendered only when `has_clearance`; shows outstanding fuel exceptions and recoveries when blocked. | 120/60s |
| `apex.salis.api.driver_portal.get_my_clearance_certificate` | `pages/Profile.vue:258-265` | — | POST, explicitly. Returns `certificate_url`, opened with `window.open(url, "_blank", "noopener")`. The URL is **never** bound to an `href` — a print key must be minted by a deliberate click, not leaked into the DOM. | 10/60s |
| `apex.salis.api.driver_portal.request_license_renewal` | `pages/Profile.vue:314-318` | — | POST. Button shown only within 30 days of expiry. | 10/60s |
| `apex.salis.api.driver_portal.get_my_vehicle` | `pages/Vehicle.vue:147-150` | — | `{vehicle}` incl. `compliance[]` with `state` and `days_to_expiry`. | 120/60s |
| `apex.salis.api.driver_portal.report_vehicle_problem` | `pages/Vehicle.vue:154-162` | `subject` (a translated constant), `description` | POST. Toast, clear, collapse the form. | 10/60s |
| `apex.salis.api.driver_portal.get_push_config` | `src/push.js:37` | — | `{enabled, vapid_public_key, subscribed}`. Gates whether the opt-in card renders at all. | 120/60s |
| `apex.salis.api.driver_portal.save_push_subscription` | `src/push.js:67-70` | `endpoint`, `p256dh`, `auth`, `user_agent` | POST after `Notification.requestPermission()` and `pushManager.subscribe`. Server refuses when VAPID is unconfigured or the endpoint host is not allow-listed. | 10/60s |
| `apex.salis.api.driver_portal.delete_push_subscription` | `src/push.js:87-90` | `endpoint` | POST, then `sub.unsubscribe()`. Both failures swallowed so the toggle always settles. | 30/60s |

### The shared build

`/driver` and `/masar` are **one bundle**, `worker_portal`. `frontend/driver` has **no `package.json`, no `vite.config.js`, no `index.html`** — it is not a buildable unit. The single entry is `frontend/worker/src/main.js`, which reads `window.holder_type` (set by the host page) through `frontend/worker/src/holder.js:2-6` and dynamically imports the driver tree:

```
frontend/worker/src/main.js:6-13
if (IS_DRIVER) {
  const [{ default: App }, { default: router }, { initPwa }] = await Promise.all([
    import("../../driver/src/App.vue"),
    import("../../driver/src/router.js"),
    import("../../driver/src/pwa.js"),
  ]);
  await import("../../driver/src/index.css");
  bootstrapPortal({ App, router, setup: () => initPwa() });
}
```

The driver's chunks therefore land beside the worker's in `apex/public/worker_portal/assets/` under de-duplicated names (`App2.js`, `Home2.js`, `i18n2.js`). Both host pages load the **same** `/assets/apex/worker_portal/assets/index.js` and `index.css`.

Consequences a rebuilder must know:

- One build run stamps **both** service workers. `frontend/worker/vite.config.js:7` declares `serviceWorkers: ["driver_portal", "worker_portal"]`, and `frontend_shared/vite.base.js:11-31` writes `apex/www/driver-sw.min.js` and `apex/www/masar-sw.min.js` from one build id computed over the **entire** emitted tree (`frontend_shared/sw.build-id.js`). CI encodes the same pairing (`.github/workflows/portal-bundles.yml:30-32`). A change in Masar invalidates the driver's caches and vice versa — which is also the mechanism that guarantees a security fix in a lazily-loaded driver chunk actually reaches installed devices.
- The `dedupe` list (`vite.base.js:77`) pins one copy of `vue`, `vue-router`, `frappe-ui` and `socket.io-client` across both trees.
- Both portals' initial CSS is one file, so a driver-only style change ships to every worker.
- Splitting them is possible, but `sw.params.js`, the CI matrix row, and the single `manifest.webmanifest` must be split with them.

---

## 3. Who opens it

**Identity is a bearer token, not a login.** Drivers are `Salis Driver` records, not Frappe `User`s — `apex/www/driver.py:4-7` calls this the "full barcode cutover". The page is served to Guest.

The exact gate, `apex/www/driver.py:32-54`:

```
context.no_cache = 1
context.csrf_token = get_csrf_token()
raw_token = frappe.form_dict.get("d") or ""
valid_token = raw_token if _TOKEN_RE.match(raw_token) else ""      # ^[A-Za-z0-9_-]{1,128}$
if valid_token:
    throttle_entry_token(DRIVER, valid_token)
    _set_token_cookie(valid_token)
    frappe.local.flags.redirect_location = "/driver"
    raise frappe.Redirect
conf = frappe.get_site_config()
context.site_name = frappe.local.site
context.socketio_port = cint(conf.get("socketio_port")) or 9000
context.async_enabled = not cint(conf.get("disable_async"))
context.dev_server = 1 if frappe.conf.developer_mode else 0
context.driver_has_token = bool(_request_token_cookie())
apply_portal_appearance(context)
```

No `guest_redirect`, no role gate on the page. Access control is entirely in the endpoints.

How the token arrives:

1. A desk user with `System Manager`, `Fleet Manager`, `Fleet Project Manager` or `Fleet Supervisor` (`apex/apex_core/utils/portal_token_security.py:24-29`; the last two are confined to their own project, `:419-430`) mints a `Masar Worker Token` bound to the driver and gets `{get_url()}/driver?d=<raw>` plus a QR (`apex/apex_core/doctype/masar_worker_token/masar_worker_token.py:436-438`).
2. The driver opens the link or scans the QR. `throttle_entry_token(DRIVER, …)` resolves it so a bad token is charged to the IP window (10/minute → 429), then swallows the 403 so a well-formed link still redirects.
3. The raw token is written to cookie **`masar_dt`** (`portal_token_security.py:15`), `httponly=True`, `samesite="Lax"`, `max_age = 180 days` (`driver.py:57-71`). `secure` is set automatically on https (`frappe/auth.py:396-397`). **No `path` is passed, so it defaults to `/`.**
4. Redirect to the clean `/driver`. Unlike `masar.html`, `driver.html` sets **no** `referrer` meta.
5. The SPA sends **no token at all** on any call — there is no equivalent of Masar's `TOKEN` constant. Identity is the cookie, always.

Server-side exchange, `apex/salis/utils/__init__.py:14-34`:

```
raw, was_presented = presented_token(DRIVER)
if was_presented:
    return resolve_portal_subject(DRIVER, raw, required=True)   # a credential ALWAYS wins, or 403
return get_driver_for_session_user(user)                         # only when no credential was presented
```

`resolve_portal_subject` (`portal_token_security.py:150-196`) hashes the raw token, matches on `{token: <sha256>, enabled: 1, holder_type: "Driver"}`, asserts the exclusive binding (`holder_type == Driver`, a `driver` set, **no** `employee`, **no** `party`, **no** `party_type`), asserts `expires_on` in the future, and asserts `Salis Driver.status == "Active"`.

**There is a second identity path.** With no credential presented, a signed-in Frappe user is resolved `User → Employee → Salis Driver`. That is the legacy preview path, and it is the only reason `Unlinked.vue` and its staff desk links exist. A credential can never be overridden by it, but a rebuild must decide whether to keep it: it is why `get_driver_context` returns `is_staff`, `full_name` and `links`.

There is also a **kill switch**: `Salis Settings.enable_driver_portal`. Every action endpoint calls `_require_enabled()` first (`apex/salis/api/driver_portal/__init__.py:28-30, 59-62`) and 403s when off. `get_driver_context` deliberately does not — it returns `enabled: false` so the SPA can say so.

Boarding endpoints use a third, wider gate: `boarding._resolve_trip` (`apex/salis/api/boarding.py:233-272`) lets Salis staff act on any trip **only** when no driver credential is presented, confines a presented credential to its own driver's trips, and refuses before the trip lookup so a missing trip name cannot become an existence oracle.

---

## 4. What is required of it

A driver on a phone, without an account, has to be able to run a whole shift:

- **Start the day.** Open the app, see today, take a photo if asked, tap check in. Tap check out at the end. See the days he was marked present, late or absent.
- **Know what he is driving and whether it is legal today.** Plate, category, odometer, fuel grade, and whether the registration, insurance or inspection is expired or about to be.
- **Run each trip.** See today's trips, start one, then work through the stops — ticking each one as he serves it, with a map link for each pickup and one link for the whole route.
- **Get his passengers on board, and prove who was.** Scan each man's code with the camera, or tick names off a list when scanning is not possible. See who has confirmed himself, who is still missing and who has asked him to wait. Nudge the missing ones. If a man was marked on board by mistake, take him back off. Then press depart, and the manifest closes with a count of who boarded and who did not.
- **Get fuel.** See what is left of the month's litres, ask for more, and see whether the request was approved.
- **Report a fault and follow it.** Describe a problem on the vehicle, or raise a support ticket with a photo, then read the replies and answer them.
- **Look after his own papers.** See when his licence expires and ask for a renewal in one tap. See whether his exit clearance is blocked and why, and download the certificate once it is issued.
- **Be told things while the phone is in his pocket** — a trip change, a boarding event, a reminder — through notifications he opted into.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what it is |
|---|---|---|
| httpOnly token cookie | **Yes** | `masar_dt` (`portal_token_security.py:15`, re-exported as `DRIVER_TOKEN_COOKIE` from the token DocType and imported by `driver.py:21-23`), `httponly`, `SameSite=Lax`, 180-day `max_age`, auto-`secure` on https, path `/`. Set only by `apex/www/driver.py:57-71`. |
| Redirect that strips the token | **Yes** | `driver.py:42-43` — charset check, throttle, cookie, `raise frappe.Redirect` to `/driver`. The QR is printed and photographed; the raw token must not survive in history. |
| Entry throttle | **Yes** | `throttle_entry_token(DRIVER, …)` before the cookie (`driver.py:40`). |
| CSRF propagation | **Yes** | `get_csrf_token()` (`driver.py:35`) → `window.csrf_token` (`driver.html:15`) → `X-Frappe-CSRF-Token` on every request (frappe-ui). Roughly half this portal's surface is POST; every one of them fails without it. `context.no_cache = 1` (`driver.py:34`) keeps the shell — and the token in it — out of any cache. |
| Server-side row scoping | **Yes** | Credential-first `_resolve_driver()` on every endpoint; the client never sends a driver id. Trip-level scoping is `_resolve_my_trip` / `boarding._resolve_trip`, which filter `{name, driver}` **jointly** rather than fetching then checking. Push subscriptions additionally refuse an endpoint already owned by another driver (`driver_portal/__init__.py:476-480`). |
| Actor-resolved scan throttle | **Yes** | `scan_boarding_pass` authorizes before it throttles (`apex/salis/api/boarding.py:408-413`, `:123-136`, `:167-189`): a rejected caller is charged against a per-IP window, an accepted one against their resolved driver-or-staff identity. The IP limiter explicitly declines to count a request with no address rather than pooling every addressless caller into one bucket (`:172-189`). This is the one throttle in either portal that is not the shared decorator, and the comments say why. |
| Realtime rooms and teardown | **Yes — this is the portal's distinguishing capability** | `driver.html:20-25` publishes `window.driver_socket = {site_name, socketio_port, enabled, dev_server}` from the site config. `src/realtime.js:4-9` binds the shared factory to room doctype `"Dispatch Trip"`, primary event `driver_trip_update`, and extra events `boarding_update`, `wait_request`, `boarding_confirmed`, `boarding_unmarked`. `frontend_shared/realtime.js:26-77` connects with `withCredentials: true`, emits `doctype_subscribe` on **both** `connect` and `reconnect`, and returns a teardown that emits `doctype_unsubscribe`, `socket.off()`s every event and disconnects. Two components connect independently (`Trips.vue:299-306` and `BoardingManifest.vue:192-214`) and each tears down in `onUnmounted`. `bootstrap.js:18` passes `socketio: false` **precisely so** frappe-ui does not open a second, unmanaged socket — that comment (`bootstrap.js:11-14`) is load-bearing. |
| Offline drafts / queues | **No** | Nothing is queued and nothing is retried. The offline banner (`App.vue:31-34`) only warns. |
| Offline data cache | **No — deliberately absent, and this is a security decision** | `src/cache.js:5` calls `purgeDriverPayloadStorage(localStorage)` at module load, which deletes every `salis_portal_cache:` key (`frontend_shared/driverStorage.js:3-16`). The service worker declares `cacheData: false` and forces network-only for three API prefixes (`sw.params.js:13-17`). A driver whose credential is swapped must never render the previous driver's trips, workers or phone numbers. This is asserted by `frontend_shared/driver-storage.security.test.mjs` and `frontend_shared/sw.security.test.mjs:149-172`. **Any rebuild that adds a stale-read cache here reopens a closed hole.** |
| PWA cache & SW scope | **Yes** | `apex/www/driver-sw.min.js` registered at root with `{scope: "/driver"}` (`driver.html:35`). Generated — never hand-edited — from `frontend_shared/sw.template.js` + the `driver_portal` entry in `sw.params.js:4-21`. Distinguishing parameters: `cacheData: false`; `networkOnlyApiPrefixes` covering `driver_portal.`, `boarding.` and `boarding_flow.`; `skipWaitingOnInstall: true` so a security build takes control without waiting for a user gesture; caches namespaced `driver-pwa-` and versioned `driver-pwa-v1-<build>` so activation drops the driver's own stale caches and provably leaves `masar-pwa-*` alone; `enablePush: true`; no self-hosted fonts in the precache list. |
| Update behaviour | **Yes** | `src/pwa-updates.js:4-6` → `createPwaUpdates({ autoActivate: true })`. On `controllerchange` the page reloads itself (`@shared/pwaUpdates.js:56-61`) — the opposite of Masar's banner. The banner markup at `App.vue:4-8` is vestigial under `autoActivate`. Paired with `skipWaitingOnInstall: true`, this is what makes a driver-side fix reach an installed phone without the driver's cooperation. |
| Install prompt | **Yes** | `src/pwa.js` captures `beforeinstallprompt`, exposes `promptInstall`, and remembers a dismissal under `salis_portal_install_dismissed`. Rendered by `InstallHint.vue` above the router view. Masar has no equivalent. |
| Web Push | **Yes** | `src/push.js` end to end: capability probe (`serviceWorker` + `PushManager` + `Notification`), config fetch, `Notification.requestPermission()`, `pushManager.subscribe` with a VAPID key converted from base64url, POST of `{endpoint, p256dh, auth, user_agent}`, and a disable path that both deletes server-side and calls `sub.unsubscribe()`. The service-worker half is generated: a `push` handler and a `notificationclick` handler that focuses an existing `/driver` window, navigates it to the payload's deep link, or opens a new one (`sw.template.js:59-104`). Both halves are inert when the owner has not configured VAPID. |
| Camera and evidence contract | **Yes — three separate places** | (a) **Boarding scan**: `BoardingScanner.vue` requires `window.BarcodeDetector` **and** `getUserMedia`, opens `facingMode: "environment"`, decodes in a `requestAnimationFrame` loop, and — critically — releases every track in `onBeforeUnmount` and pauses the camera the moment a code is submitted (`:161-186`). An unsupported browser gets a named message, a denied permission gets a different one. No decoding library is bundled; the browser API is the dependency. (b) **Attendance photo** and (c) **ticket photo**: `<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment">` — `capture` is what makes it open the camera rather than the gallery — read to a base64 data URI by `src/upload.js` with a typed `UnsupportedPhotoType` error so the UI can say *why*. The server proves the bytes with PIL and saves a **private** File (`driver_portal/images.py:66-163`). |
| GPS contract | **Yes** | `pages/Trips.vue:308-342`. Tracking starts **only** on a successful `start_my_trip`, pushes immediately then every 30 s, uses `{enableHighAccuracy: true, maximumAge: 15000, timeout: 10000}`, stops on completion of that trip, and stops in `onUnmounted`. Permission denial and push failure are both silent — a driver must never be blocked from finishing a trip because location was refused. |
| Deep links / bookmarks | **Yes** | `/driver#/`, `#/attendance`, `#/trips`, `#/trips?tab=recent`, `#/trips?trip=<DT-name>` (trip selection is a **query param**, so an open detail pane is itself linkable — `Trips.vue:198-208`), `#/route`, `#/route/<DT-name>`, `#/fuel`, `#/tickets`, `#/profile`, `#/vehicle`. Plus the entry form `/driver?d=<token>` printed on every QR, and the plain `/driver`. Push notifications carry their own deep link into this set (`sw.template.js:77`). |
| Language propagation | **Yes** | Two languages: `en`, `ar` (`src/i18n.js:4-5`), stored under `localStorage` key **`salis_portal_lang`** (Masar uses a different key, so the two portals remember separately on one device). `useDocumentLanguage` writes `<html lang>`/`<html dir>`; `call.js` echoes it as `_lang` on every request. `App.vue:103-105` additionally re-applies `window.portal_theme` to `data-theme` if the server template did not. |
| Theme / brand | **Yes** | `apply_portal_appearance` → `data-theme`, `window.portal_logo`, `window.portal_show_brand`, `window.portal_theme` (`driver.html:3,17-19`). Consumed by `Unlinked.vue` via props from `App.vue:130-131`. |
| Kill switch | **Yes** | `Salis Settings.enable_driver_portal`. `_require_enabled()` guards every action endpoint; `get_driver_context` reports `enabled: false` instead of throwing so the SPA can explain rather than break. |
| Ticket pagination correctness | **Yes** | `src/ticketPagination.js` plus a generation counter (`Tickets.vue:238, 244-246, 285`). Every ticket open/close/reply bumps the generation, and every async callback checks `isCurrentTicketRequest` before writing state. This is what stops a slow page-2 response from a *previous* ticket landing in the currently open one. `mergeCommunicationPages` de-duplicates by `name` and re-sorts by `(communication_date, creation, name)`. It exists because the naive version showed one driver's conversation under another ticket. |

---

## 6. What is deliberately dropped

| Drop | Evidence |
|---|---|
| The vestigial update banner | `App.vue:4-8` renders a "reload" banner bound to `updateReady`, but `pwa-updates.js:4-6` sets `autoActivate: true`, and under that flag `trackInstalling` never sets `updateReady` (`@shared/pwaUpdates.js:16`) and `controllerchange` reloads unconditionally. The banner cannot appear. Drop the markup, keep the auto-activation. |
| `mini-ok` style | `components/BoardingManifest.vue:302-305` defines `.mini-ok`; the template only ever uses `.mini-no` (`:46`). No other file references it. |
| `.stale-note` in the driver Route page | `pages/Route.vue:314-324` styles a stale-data note. The driver portal has no stale data by design (`src/cache.js`) and the class appears nowhere in that template. It is a copy of Masar's. |
| The offline copy | `src/i18n.js` `offline.banner` reads "Showing saved data; changes are paused" and `offline.stale` reads "Offline — showing last saved data." Neither is true: the driver portal saves nothing. The strings actively mislead a driver into thinking a screen is trustworthy when it is empty. |
| `t("trips.scanBoarding", "Scan Boarding")` / `t("trips.manualBoarding", "Manual Boarding")` | `components/BoardingManifest.vue:16,19` pass a second argument to `t`. The shared `translate(key, params)` (`frontend_shared/i18n.js:39-44`) treats the second argument as an **interpolation params object**, not a default. The English literal is silently discarded; if those keys are missing the raw key string renders. |
| The signed-in preview identity path | `apex/salis/utils/__init__.py:25` → `get_driver_for_session_user`, and everything downstream of it: `Unlinked.vue`'s staff panel, `_is_staff`, `_staff_links` (`driver_portal/__init__.py:64-92`), and the `is_staff`/`full_name`/`links` keys on `get_driver_context`. The module docstring calls this the "legacy signed-in preview path" (`driver_portal/__init__.py:4-6`) and `driver.py:4` says the cutover to tokens is complete. Decide explicitly whether it stays; roughly a screen and three helpers hang off it. |
| Notifications for a token-only driver | `get_my_notifications` returns `[]` unless `Salis Driver.driver_user` is set and is not Guest (`driver_portal/notifications.py:57-59`). Under the barcode cutover a driver has no user, so the Home notifications card is permanently empty for exactly the population this portal was built for. Either notifications move onto a driver-keyed channel, or the card goes. |

---

## Defects found while reading

1. **The driver PWA installs as "Masar" and opens the worker portal.** `apex/www/driver.html:8` links `/assets/apex/worker_portal/manifest.webmanifest`, whose contents are `"name": "Masar"`, `"short_name": "Masar"`, `"start_url": "/masar"`, `"scope": "/masar"`, with Masar icons (`frontend/worker/public/manifest.webmanifest:2-23`). A driver who accepts the install prompt that `InstallHint.vue` shows him gets a home-screen icon labelled Masar that launches the worker portal. The scope mismatch also means the installed app is not scoped to `/driver` at all. One manifest cannot serve two portals; the shared build needs two.

2. **No catch-all route.** `src/router.js:4-19` ends without a `/:pathMatch(.*)*` entry (Masar has one at `router.js:13`). Any unknown hash — a stale bookmark, a renamed screen, a typo in a pushed deep link — renders the shell with an empty `<router-view>` and no way back except the bottom bar.

3. **`driver.html` sets no `referrer` policy.** `masar.html:6` sets `<meta name="referrer" content="no-referrer">`; `driver.html` does not. The redirect gets the token out of the URL quickly, but for the duration of the `?d=` request — and for any external link clicked before it — the driver page is a normal referrer source. The two host pages should agree.

4. **`notify_window_seconds` is a dict on the worker's poll.** Not this portal's screen, but this portal's flow. `apex/salis/api/boarding_flow.py:660` binds `window` to the notify-window seconds and `:675` rebinds the same name to the `boarding_window.resolve(...)` dict; `:682` and `:689` then emit that dict as `notify_window_seconds`. The worker's countdown renders `NaN`. Driver-side reads are unaffected because `get_trip_boarding` keeps them in separate locals (`:372, :385`) — which is exactly the fix the worker path needs.

5. **Realtime events are not filtered by trip on the Trips screen.** `Trips.vue:291-297` accepts any `wait_request` on the `Dispatch Trip` room and raises the alert regardless of which trip it belongs to. `BoardingManifest.vue:194` does filter (`if (payload.dispatch_trip && payload.dispatch_trip !== props.trip) return`). A driver with two trips today sees a wait request from the wrong bus.

6. **Two sockets are open while the manifest is on screen.** `Trips.vue:301` and `BoardingManifest.vue:210` each call `connectDriverRealtime`, and the shared factory creates a new `io()` connection per call (`frontend_shared/realtime.js:32`). Both subscribe to the same room and both receive every event, so `panel.reload()` and `today.reload()` fire in duplicate on each boarding event. Teardown is correct on both, so it is waste rather than a leak.

7. **`resultClass` / `resultIcon` / `resultTitleKey` / `resultHintKey` are plain functions, not computeds.** `components/BoardingScanner.vue:80-83` returns arrow functions; the template binds `:class="resultClass"` (`:23`) and `:name="resultIcon"` (`:24`) — so Vue receives the **function object**, not its return value. The scan-result card gets no tone class and no icon name. `{{ t(resultTitleKey) }}` (`:25`) passes a function to `t`, whose `key.split(".")` will throw. The result screen is broken for every outcome.

8. **`Attendance.vue` shadows its own error variable.** `:141` declares `catch (err)` inside `onPhoto`, shadowing the module-level `const err = ref("")` declared at `:124`. The `catch` block then assigns to `photoError`, so nothing breaks today, but the shadow makes `err` unreachable from that block — and `err` is what the `ErrorState` at `:8` renders.

9. **The clearance certificate opens in a new tab from an async callback.** `pages/Profile.vue:262` calls `window.open` inside `onSuccess`, i.e. outside the user-gesture window. Mobile Safari and Chrome pop-up blockers will suppress it. The mint-on-POST design is right; the delivery is not.
