# Masar (`/masar`) — capability record

Masar is the phone app a housed and transported worker opens from his own private link to see where he sleeps, when his bus leaves, what he is holding, and to ask for something.

---

## 1. What it does

Seven screens behind a hash router (`frontend/worker/src/router.js:5-13`). Three are in the bottom bar (`frontend/worker/src/App.vue:167-171`); the rest are reached from cards and links.

| Route | Screen | The decision or task it serves |
|---|---|---|
| `#/` | Home | "What do I do next?" One dock button whose label is computed from the ride state: no ride → request one; ride `Dispatched` → open the boarding pass; otherwise → view the ride (`pages/Home.vue:150-159`). Also carries the document-expiry alert with a one-tap "notify HR", the bed chip, contacts, and an open-request count. |
| `#/transport` | Transport | "Where is my bus and am I counted on it?" Upcoming and past trips, the live boarding flow for the first upcoming trip, and a 1–5 star rating on a fulfilled past trip that has a dispatch trip and is not yet rated (`pages/Transport.vue:180-182`). |
| `#/request-transport` | Request transport | "I need a ride that is not scheduled." Service line, from/to, pickup time, reason, plus rows for unregistered co-passengers (name + ID number are required for a row to be sent — `pages/RequestTransport.vue:131-133`). |
| `#/profile` | Profile | "Are my papers still valid?" Identity fields, Iqama/passport with days-to-expiry colouring, language switch, links onward. Renders from the `ctx` prop the shell already loaded — **it makes no call of its own**. |
| `#/accommodation` | Accommodation | "Which building, room, bed am I in, and who do I call?" Building in-charge with tel: and WhatsApp buttons, map link, check-in date, notes. |
| `#/custody` | Custody | "What am I still holding?" Net-balance custody articles with quantity, issue date and issuer. |
| `#/requests` | Requests | "Report a problem / ask for something." Category, priority, location, preferred language, subject, description, one optional photo; below it the worker's own request list. |
| `#/requests/:name` | Request detail | "What happened to my request?" Status, a reconstructed timeline, triage and resolution notes, attachment. |
| any other hash | — | Redirects to `#/` (`router.js:13`). |

**Findings on screens that serve nothing.**
- `pages/Custody.vue:49-51,96` ends with an "Acknowledge receipt" button pointing at `/my-custody-acknowledgment`. That route is a Frappe Web Form with `"login_required": 1` (`apex/habitat/web_form/my_custody_acknowledgment/my_custody_acknowledgment.json:75`). Masar workers are not Frappe users, so this button is a guaranteed dead end — it lands the worker on `/login`.
- `components/BoardingFlow.vue:38-44` renders a "your driver has arrived" panel driven by `boarding.driver_arrived`. That flag is only ever set by `apex.salis.api.driver_portal.mark_arrived`, and **no shipped frontend calls it** (grep for `mark_arrived` across `frontend/` returns nothing). The panel is unreachable in the shipped product.
- `components/DestinationsCard.vue:36-39` hardcodes `count: 0` for three of its four rows; only the requests count is live.

---

## 2. How it works

Every call goes out through `frappe-ui`'s `createResource`, which posts to `/api/method/<dotted path>`. The shared fetcher appends the current `<html lang>` as `_lang` on every request (`frontend/frontend_shared/call.js:12-20`) — that is the framework's own language selector (`frappe/translate.py:46`), so server-side `_()` answers in the worker's chosen language.

`configureApi()` runs **before** the frappe-ui plugin is installed, and the plugin is installed with `socketio: false` (`frontend/frontend_shared/bootstrap.js:15-23`). The worker portal has no socket at all — it is a Guest and Frappe's socket rooms are user-scoped.

All 18 endpoints below are `@frappe.whitelist(allow_guest=True)` and carry an identity-scoped `@rate_limit`. **No exceptions found.**

| Dotted path | Called from | Sends | What the client does with the answer | Limit |
|---|---|---|---|---|
| `apex.salis.api.masar.get_worker_context` | `App.vue:134-139` | `token: ""` | Gates the whole shell: no `data.employee` → error screen. Feeds the header name/photo and the Profile screen via a prop. Re-polled every 45 s while the tab is visible (`@shared/usePoll.js`). | 60/60s |
| `apex.salis.api.masar.get_enum_labels` | `App.vue:104-116` | `lang` | Only when language ≠ `en`. Fills the client's enum-label map so server Select values render translated. No identity; public by design (`masar.py:234-252`). | 30/60s |
| `apex.salis.api.masar.get_worker_home` | `pages/Home.vue:100-105` | `token: ""` | `next_ride`, `bed`, `profile_alerts`, `open_request_count`, `iqama_days_left` → the whole Home screen. | 60/60s |
| `apex.salis.api.masar.get_worker_contacts` | `pages/Home.vue:107-112` | `token: ""` | Building in-charge / today's driver / housing office → contacts card. Failure is isolated (its own retry) so Home still paints. | 60/60s |
| `apex.salis.api.masar.notify_hr_iqama_expiring` | `pages/Home.vue:165-180` | `token: ""` | POST. `{notified: bool}` → success or "couldn't notify HR". Server re-reads the expiry and refuses outside 30 days, so the client cannot force an alert. | 6/hour |
| `apex.salis.api.masar.get_worker_accommodation` | `pages/Accommodation.vue:120-132` | `token: ""` | On success caches to `localStorage`; on failure falls back to that cache and shows a "stale" strip. | 60/60s |
| `apex.salis.api.masar.get_worker_custody` | `pages/Custody.vue:75-87` | `token: ""` | Same success-cache / stale-fallback pattern. | 60/60s |
| `apex.salis.api.masar.get_worker_transport` | `pages/Transport.vue:237-249` | `token: ""` | `upcoming` / `past` partitions. Same stale-cache pattern. Pull-to-refresh re-fetches it. | 60/60s |
| `apex.salis.api.boarding_flow.worker_trip_boarding` | `pages/Transport.vue:281-291` | `token: ""` | The live poll. Drives status, the departure countdown, the wait counter, the wrong-bus panel, and the five-state `boarding_window` verdict. Cadence comes **from the response** (`poll_seconds`, default 10 s) and only runs while `document.hidden` is false and the state is unsettled (`Transport.vue:294-323`). | 120/60s |
| `apex.salis.api.masar.confirm_boarding` | `pages/Transport.vue:328-345` | `token`, `transport_request` | POST. The "I'm at the pickup" button on trips **other than** the first upcoming one. `{dispatch_trip}` present → confirmed. | 12/hour |
| `apex.salis.api.boarding_flow.worker_claim_boarded` | `components/BoardingFlow.vue:203-216` | `token: ""` | POST. The "I'm on the bus" button on the active trip. Emits `refresh` so the poll re-reads. | 30/60s |
| `apex.salis.api.boarding_flow.worker_request_wait` | `components/BoardingFlow.vue:219-233` | `token: ""` | POST. "Wait for me." Updates the local wait counter from `wait_count`; button disables at `wait_max`. | 30/60s |
| `apex.salis.api.masar.get_worker_boarding_pass` | `components/BoardingFlow.vue:242-263` | `token: ""` | Lazy — fetched only when the worker taps "show pass". `pass.qr_payload` is rendered as a QR by a hand-written encoder; `expires_in_hours` is shown. | 60/60s |
| `apex.salis.api.masar.submit_trip_rating` | `components/TripRating.vue:74-85` | `dispatch_trip`, `transport_request`, `rating`, `feedback` | POST. **Sends no `token` argument** — relies entirely on the cookie. Server re-checks manifest membership and one-rating-per-trip. | 10/60s |
| `apex.salis.api.masar.list_worker_requests` | `pages/Requests.vue:200-204` | `token: ""` | The worker's own request list, newest first, capped at 50 server-side. | 60/60s |
| `apex.salis.api.masar.create_worker_request` | `pages/Requests.vue:208-224` | `token`, `category`, `priority`, `issue_location`, `preferred_language`, `subject`, `body`, `photo` (data URI), `photo_filename` | POST. Clears the form, shows a 3 s confirmation, reloads the list. | 10/hour |
| `apex.salis.api.masar.get_worker_request_detail` | `pages/RequestDetail.vue:112-116` | `token`, `name` (from the route) | Full request + timeline. Server matches on `{name, employee}` together, so a foreign name simply does not resolve. | 60/60s |
| `apex.salis.api.masar.create_worker_transport_request` | `pages/RequestTransport.vue:120-129` | `token`, `service_line`, `from_location`, `to_location`, `pickup_datetime`, `purpose`, `adhoc_passengers` (JSON) | POST. Swaps the form for a confirmation panel. | 6/hour |

### The shared build

`/masar` and `/driver` are **one bundle**, `worker_portal`. `frontend/worker/vite.config.js:4-8` is the only Vite config; `frontend/driver` has no `package.json` and no config of its own. `frontend/worker/src/main.js:5-22` reads `window.holder_type` (via `src/holder.js:2-6`) and dynamically imports either `./App.vue` + `./router.js` + `./index.css`, or `../../driver/src/{App.vue,router.js,pwa.js,index.css}`. Rollup therefore emits the driver's chunks alongside the worker's in `apex/public/worker_portal/assets/` (`App2.js`, `Home2.js`, `i18n2.js`, …).

For a rebuild this means: **the two portals share one output directory, one `index.css` URL, one `index.js` URL, and one build id.** The build id is a hash of the *whole* emitted tree (`frontend_shared/sw.build-id.js`), and one build run stamps **both** service workers (`vite.config.js:7`, `frontend_shared/vite.base.js:11-31`). Changing anything in the driver changes Masar's service-worker bytes and invalidates Masar's caches, and vice versa. Splitting them into two builds is a real option, but then `sw.params.js`, the CI matrix entry (`.github/workflows/portal-bundles.yml:30-32`), and the single `manifest.webmanifest` all have to be split with them.

---

## 3. Who opens it

**Identity is a bearer token, not a login.** The worker is an `Employee`; he is never a Frappe `User`. The page is served to Guest.

The exact gate, `apex/www/masar.py:35-53`:

```
context.no_cache = 1
context.csrf_token = get_csrf_token()
raw_token = frappe.form_dict.get("w") or ""
valid_token = raw_token if _TOKEN_RE.match(raw_token) else ""      # ^[A-Za-z0-9_-]{1,128}$
if valid_token:
    throttle_entry_token(WORKER, valid_token)
    _set_token_cookie(valid_token)
    frappe.local.flags.redirect_location = "/masar"
    raise frappe.Redirect
context.masar_has_token = bool(_request_token_cookie())
apply_portal_appearance(context)
```

There is **no `guest_redirect`** and **no role gate**. Anyone may load the shell; the shell is useless without a cookie.

How the token arrives, in order:

1. A desk user with an issuer role mints a `Masar Worker Token` and gets back `{get_url()}/masar?w=<raw>` plus a QR (`apex/apex_core/doctype/masar_worker_token/masar_worker_token.py:320-322`, `:360-384`). Issuer roles and their building scoping live in `apex/apex_core/utils/portal_token_security.py:17-30`, `:370-433`. Only the hash is stored for matching; an encrypted copy exists so the *same* link can be re-shared.
2. The worker opens the link. `throttle_entry_token` (`portal_token_security.py:199-209`) runs the full resolve so a bad token is charged against the caller's IP window (10 bad tries/minute → 429), then swallows the 403 so a well-formed link always redirects.
3. The raw token is written to cookie `masar_wt`, `httponly=True`, `samesite="Lax"`, `max_age = 180 days` (`masar.py:31-32,64-70`). `secure` is not passed, but Frappe sets it automatically on an https request (`frappe/auth.py:396-397`). **No `path` is passed, so the cookie defaults to `/`** — it is sent on every request to the site, not only `/masar`, despite what the docstring says.
4. The browser is redirected to the clean `/masar`. The secret is out of the address bar, out of history, out of the Referer (`masar.html:6` also sets `referrer: no-referrer`).
5. Every subsequent API call sends **`token: ""`** (`frontend/worker/src/utils/token.js:13`). The SPA never holds the secret. `_token_from_request` (`apex/salis/api/masar_worker.py:68-71`) falls back to the cookie.

Server-side exchange, `portal_token_security.py:150-196`: SHA-256 the raw token, look up `Masar Worker Token` on `{token: <hash>, enabled: 1, holder_type: "Worker"}`, assert the exclusive subject binding (`holder_type == Worker`, `party_type == Employee`, `party == employee`, **no** `driver`), assert `expires_on` is in the future, assert the `Employee.status == "Active"`. Any failure charges the throttle and raises `PermissionError`. Tokens are revoked automatically when the Employee stops being Active (`portal_token_security.py:341-355`).

`window.masar_has_token` (`masar.html:19`) is a boolean only, and drives the "no link" screen (`App.vue:24-33`).

---

## 4. What is required of it

A worker who lives in company housing and rides a company bus has to be able to do these things from his own phone, in his own language, without an account:

- **Know when his bus goes and prove he is on it.** He opens the app, sees the next ride with the driver's name and phone, taps to call or WhatsApp, and — while the bus is actually at *his* pickup — taps one button that puts him on the manifest. If he is late he taps "wait for me". If he boarded the wrong bus the app tells him which bus is his and gives him that driver's phone. If he can only show a code, he opens his boarding pass and the driver scans it.
- **Know where he sleeps and who to call about it.** Building, room, bed, the person in charge, and a map link.
- **Know if his papers are about to expire, and tell HR in one tap.**
- **Say something is broken.** Pick a category, describe it, add a photo from the camera, send. Then check later what was done about it.
- **Ask for a ride that nobody scheduled**, and add the men travelling with him who are not on any list yet.
- **See what tools and kit are still signed out in his name.**
- **Say whether the ride was any good** once it is finished.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what it is |
|---|---|---|
| httpOnly token cookie | **Yes** | `masar_wt`, `httponly`, `SameSite=Lax`, 180-day `max_age`, auto-`secure` on https, path `/`. Set only by `apex/www/masar.py:56-70`. The SPA must never read or resend it. |
| Redirect that strips the token | **Yes** | `masar.py:47-48` — validate charset, cookie it, `raise frappe.Redirect` to `/masar`. Plus `<meta name="referrer" content="no-referrer">` (`masar.html:6`). Without both, the personal secret sits in browser history and in any outbound Referer. |
| Entry throttle | **Yes** | `throttle_entry_token(WORKER, …)` before the cookie is set (`masar.py:45`). Bad links are charged to the IP window; the 11th in a minute gets 429. A rebuild that cookies first and validates later loses the only brake on link-guessing. |
| CSRF propagation | **Yes** | `context.csrf_token = get_csrf_token()` (`masar.py:40`) → `window.csrf_token` (`masar.html:17`) → frappe-ui adds `X-Frappe-CSRF-Token` on every request (`frappe-ui/src/utils/frappeRequest.js:19-20`). Every POST endpoint listed above dies without it. Note `context.no_cache = 1` (`masar.py:37`) — the shell must never be cached with someone else's CSRF token in it. |
| Server-side row scoping | **Yes** | Every endpoint calls `_resolve_worker(token)` → `resolve_portal_subject(WORKER, …)` and filters on that Employee. The client sends **no** employee id anywhere. `get_worker_request_detail` is the pattern to copy: it matches `{name, employee}` jointly rather than fetching then checking. |
| Realtime rooms / teardown | **No** | Masar has no socket. `bootstrap.js:18` passes `socketio: false`, and `masar.html` sets no socket globals. Freshness is polling only: 45 s on the shell context (`@shared/usePoll.js` — visibility-aware, single-flight, cleared on unmount) and a server-dictated `poll_seconds` on the boarding state (`Transport.vue:302-323`, `clearInterval` on unmount). Both must stay visibility-aware or a phone in a pocket burns the rate limit. |
| Offline drafts / queues | **No** | Nothing is queued. A write attempted offline fails and shows an error. Reads degrade to cache (below); writes do not. |
| Stale-read cache | **Yes** | `localStorage` under prefix `masar_portal_cache:` (`src/utils/cache.js`, `@shared/makeCache.js`) for `get_worker_transport`, `get_worker_accommodation`, `get_worker_custody`. On a failed reload the last payload is rendered behind a "showing last saved data" strip. See the defect below before copying this. |
| PWA cache & SW scope | **Yes** | `apex/www/masar-sw.min.js` registered at root with `{scope: "/masar"}` (`masar.html:31`). Generated — never hand-edited — from `frontend_shared/sw.template.js` + the `worker_portal` entry in `frontend_shared/sw.params.js:23-51`. Its distinguishing behaviour: `cacheData: true` with six named data endpoints cached network-first under a **synthesised GET key** built from path + request body (frappe-ui posts, and the Cache API cannot store a POST); `skipWaitingOnInstall: false` so the SPA's reload banner decides when a new build takes over; self-hosted Cairo + Montserrat subsets cache-first; caches namespaced `masar-pwa-` and version-prefixed `masar-pwa-v3-<build>` so activation drops only Masar's own stale caches and never the driver's. |
| Update banner | **Yes** | `src/pwa.js` → `createPwaUpdates()` with `autoActivate` **false** (the driver's is true). A waiting worker sets `updateReady`; the banner posts `SKIP_WAITING` and reloads on `controllerchange` (`@shared/pwaUpdates.js:76-83`). A worker mid-boarding must not be reloaded out from under. |
| Camera / evidence contract | **Yes** | One optional photo on a resident request. Client: `<input type="file">` with `accept="image/jpeg,image/png,image/webp"`, extension **and** MIME both checked (`@shared/photoFile.js`), 8 MB ceiling, read to a base64 data URI (`pages/Requests.vue:167-198`). Server: `_attach_worker_photo` (`apex/salis/api/masar_worker.py:266-300`) calls `verified_image_type(photo, max_bytes=WORKER_PHOTO_MAX_BYTES)` — 8 MB, matching the client — which opens the bytes with PIL, checks the real format against the declared one, rejects trailing bytes after the container, and caps 8192 px / 20 Mpx (`apex/salis/api/driver_portal/images.py:66-128`). It then **discards the client filename** and rebuilds it from a sanitised stem plus the verified extension, so a name cannot launder a type, and saves a **private** File. Both halves must survive; the client check is convenience, the server check is the contract. Note the worker input has **no** `capture="environment"` — unlike the driver's, it opens the gallery, not the camera. |
| Boarding QR | **Yes** | `components/QrCode.vue` renders `pass.qr_payload` with a hand-written byte-mode QR encoder (`src/utils/qrcode.js`, versions 1–14, mask-penalty selection) and a contrast-repair pass that forces ≥7:1 and falls back to pure black-on-white (`src/utils/qrColor.js`). It re-renders on theme change via a `MutationObserver`. This exists because a themed QR that a scanner cannot read is a worker stranded at a stop. No external QR library is in the tree. |
| Deep links / bookmarks | **Yes** | Hash routes, so the whole set is bookmarkable: `/masar#/`, `#/transport`, `#/request-transport`, `#/profile`, `#/accommodation`, `#/custody`, `#/requests`, `#/requests/<REQ-name>`. Plus the entry form `/masar?w=<token>` — which is what is printed on every QR and sent in every WhatsApp — and the plain `/masar`. The catch-all redirect to `#/` (`router.js:13`) must stay, or an old bookmark shows a blank shell. |
| Language propagation | **Yes** | Five languages: `en, ar, ur, hi, bn` (`src/i18n.js:6`), stored in `localStorage` key `masar_portal_lang`, RTL for `ar` and `ur`. `useDocumentLanguage` writes `<html lang>` and `<html dir>`; `call.js` reads that attribute back and sends `_lang` on **every** request, which is Frappe's own precedence-1 language source. Server Select options are translated once per language by `get_enum_labels` rather than duplicated in JS. Losing any link in that chain is how English leaks into an Arabic screen. |
| Theme / brand | **Yes** | `apply_portal_appearance` projects the Salis Portal Theme onto `data-theme` and `window.portal_logo` / `window.portal_show_brand` (`apex/apex_core/utils/portal_bootstrap.py:26-36`, `masar.html:3,20-21`). One Single re-skins every portal. |
| Kill switch | **No** | Unlike the driver portal (`enable_driver_portal` in Salis Settings), Masar has **no** enable flag. The only way to shut it off is to revoke tokens. |

---

## 6. What is deliberately dropped

| Drop | Evidence |
|---|---|
| `src/utils/token.js` `TOKEN` export | It is the constant `""` (`token.js:13`) and is passed as `params: { token: TOKEN }` at 14 call sites. It sends an empty string the server ignores in favour of the cookie. Delete the export; send nothing. Keep `hasToken`. |
| `src/holder.js` `HOLDER_TYPE` and `IS_WORKER` | Grep across `frontend/worker`, `frontend/driver`, `frontend/frontend_shared`: the only importer is `main.js:3`, and it imports `IS_DRIVER` only. |
| The "driver has arrived" panel | `components/BoardingFlow.vue:38-44` reads `boarding.driver_arrived`, set only by `apex.salis.api.driver_portal.mark_arrived`. `grep -rn "mark_arrived"` over the entire repo excluding `node_modules`/`__pycache__` returns the server definition, one docstring mention, and out-of-tree tests under `.claude/tests/` — **no frontend caller anywhere**. Either build the driver's arrival button or drop the panel; do not carry it forward as-is. |
| The Custody "Acknowledge receipt" link | `pages/Custody.vue:96` targets `/my-custody-acknowledgment`, a Web Form with `login_required: 1`. A tokened worker has no login. Either the flow becomes a token-scoped endpoint or the button goes. |
| Hardcoded zero counts in `DestinationsCard` | `components/DestinationsCard.vue:36-39` — three of four rows pass `count: 0`, so the badge never renders for them. Either wire them or drop the prop. |
| `apex.salis.api.masar.get_my_worker_route_summary` | `grep -rn "get_my_worker_route_summary"` finds the definition (`masar.py:133`) and two docstring mentions. No caller in any frontend or any Python module. Its own docstring says it is "for the standalone `/masar` page header" — a header that no longer exists (`masar.py:16-18` records the move to `/driver`). |
| `pages/Profile.vue` as a data screen | It defines `props.ctx` and reads nothing else. It is a pure view over `get_worker_context`. A rebuild should keep it that way rather than giving it its own fetch. |
| Nothing in the language set | Checked, not dropped: all five locales declared at `src/i18n.js:6` are genuinely authored — `en` at `:19`, `ar` at `:351`, `ur` at `:683`, `hi` at `:1003`, `bn` at `:1323`. The catalogue is one ~1600-line file; a rebuild should split it per locale but must carry all five, plus the `@shared/sharedMessages.js` fallback layer that `lookup` falls through to (`frontend_shared/i18n.js:28-32`). |

---

## Defects found while reading

1. **`notify_window_seconds` is a dict, not a number, on the worker poll.** `apex/salis/api/boarding_flow.py:660` binds `window` to the notify-window *seconds*, then line `:675` rebinds the same name to the `boarding_window.resolve(...)` **dict**. Line `:682` then passes that dict into `_state_payload(row, window_seconds)` and line `:689` sets `"notify_window_seconds": window` directly. The client does `(props.boarding?.notify_window_seconds || 0) * 1000` (`components/BoardingFlow.vue:187`) → `NaN` → the departure countdown computes `Math.max(0, Math.ceil(NaN))` = `NaN` and renders "departing in NaN seconds" whenever `notify_at` is set. Two locals, one name.

2. **The Masar service worker caches worker PII with no identity purge.** `sw.params.js:23-51` sets `cacheData: true` for six endpoints containing one worker's housing, documents, custody and manifest. The cache key is `path + "#" + body`, and the body is `{"token":"","_lang":"ar"}` — identical for every worker. The driver portal was hardened against exactly this (network-only APIs, `skipWaitingOnInstall: true`, `purgeDriverPayloadStorage` on boot, and a security test asserting it — `frontend_shared/driver-storage.security.test.mjs`, `sw.security.test.mjs:149-157`). Masar received none of it. Two workers sharing a phone, or one worker whose token is reissued to another person, read the previous worker's cached data.

3. **The same gap in `localStorage`.** `src/utils/cache.js` writes transport, accommodation and custody payloads under `masar_portal_cache:` and nothing ever clears them on a token change. This is the precise pattern `frontend_shared/driverStorage.js` exists to purge on the driver side.

4. **`/driver` installs as "Masar".** `apex/www/driver.html:8` links `/assets/apex/worker_portal/manifest.webmanifest`, whose contents are `"name": "Masar"`, `"start_url": "/masar"`, `"scope": "/masar"` (`frontend/worker/public/manifest.webmanifest:2-6`). A driver who installs the PWA gets an icon called Masar that opens the worker portal. One manifest cannot serve two scopes.

5. **`/masar` renders server strings in the session language, not Arabic.** `masar.html:3` declares `lang="ar"` and `:15` calls `{{ _("Masar") }}`, but `apex/www/masar.py` never calls `render_in_arabic()`. `apex/apex_core/utils/portal_language.py:1-13` documents this exact failure — English sentences inside an RTL box — and `safety.py:50`, `fleet_os.py:48` and `masar_supervisor.py:99` all call it. Masar does not.

6. **`submit_trip_rating` is the only worker write that sends no `token` argument.** `components/TripRating.vue:96-101`. It works today because the cookie is the fallback, but it is the one call that would break silently if the explicit-token path were ever made mandatory.

7. **`components/BoardingFlow.vue:106` shows "no pass available" on any pass error**, including a rate-limit 429 or an expired token, because `passError` is truthy for every failure and `passErrorMsg` (which does distinguish them, `:245-247`) is never rendered.

8. **The token cookie has no `path`.** `masar.py:64-70` passes no `path`, and Frappe's `set_cookie` (`frappe/auth.py:386-406`) does not set one either, so it defaults to `/`. The worker's bearer credential is attached to every request to the site — `/app`, `/api`, other portals — not just `/masar`. The docstring at `masar.py:57` calls it "the httpOnly /masar cookie", which is not what is shipped.
