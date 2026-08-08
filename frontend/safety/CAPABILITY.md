# /safety — capability

A logged-in supervisor walks one building, marks every safety task that is due this period Pass / Fail / Issue, and submits — creating one submitted Safety Round per cadence and emailing the manager a report.

---

## 1. What it does

One screen. There is no router (`src/main.js:6` calls `bootstrapPortal({ App })` with no router argument), so the whole portal is `src/App.vue` switching between four states.

| State | Condition | The decision or task it serves |
|---|---|---|
| Building choice | `!building` (`App.vue:41`) | "Which building am I inspecting today?" `@shared/components/BuildingPicker.vue`; auto-selects when exactly one building is readable (`BuildingPicker.vue:58-63`). |
| Due checklist | `due.length > 0` (`App.vue:103`) | "What is overdue *right now* for this building?" One collapsible block per due cadence, one row per catalog task, four taps per row: Pass, Fail, Issue, Note (`components/TaskRow.vue:24-65`). Tapping the same verdict again clears it (`TaskRow.vue:117-119`). |
| Nothing due | `due.length === 0` (`App.vue:91`) | "This building is up to date — is there another one I should walk?" |
| Submitted | `submitted !== null` (`App.vue:57`) | "Did it save, and did the manager actually get the email?" Shows the derived result per cadence and, separately, whether the mail was sent (`App.vue:65-84`). |

**A screen that serves nothing:** none, but the *due* state carries a promise it cannot keep. `due.draftKept` — "Your marks are kept on this device until you submit" (`src/i18n.js:44`) — is true (§5), yet the building itself is not kept, so a reload lands the supervisor back on the picker with the marks invisible until the same building is re-chosen on the same date.

**What the portal deliberately does not decide.** "Due" is a server judgement, not a client one: a cadence is due only when no *submitted* Safety Round covers the current period (`apex/habitat/api/safety_checklist.py:200-219`), and drafts and cancelled rounds do not close a period. Period boundaries — the ISO Mon..Sun week in particular, computed from `weekday()` rather than Frappe's System-Settings week start — live at `safety_checklist.py:150-197`. The portal renders `period_label` and never recomputes it.

---

## 2. How it works

| Dotted path | Verb / caller | Sends | Does with the answer | Whitelisted |
|---|---|---|---|---|
| `frappe.client.get_list` (doctype `Building`) | GET · `BuildingPicker.vue:52-67` via `createListResource` | `fields:[name,building_name]`, `orderBy:"building_name asc"`, `pageLength:99999` | The building choice list | yes — `frappe/client.py:27` |
| `apex.habitat.api.safety_checklist.get_due_cadences` | GET · `App.vue:199-202` | `{building}` | `data.due` → one block per due cadence, each with `cadence`, `period_label` and its expected `tasks` (`name`, `task_code`, `task_title`, `department`, `priority`, `instructions`, `evidence_required`) | yes — `safety_checklist.py:222` |
| `apex.habitat.api.safety_checklist.submit_due_rounds` | POST · `App.vue:315-319` | `{building, round_date: <local YYYY-MM-DD>, results: JSON.stringify([{task, cadence, execution_status, notes}])}` | Stores the whole reply as `submitted` and drops the local draft. Reads `rounds[]` (cadence + `overall_result`) and `emailed` | yes, POST-only — `safety_checklist.py:418` |

Three endpoints. All three are `@frappe.whitelist()`.

**The verdict vocabulary is translated at the boundary**, `App.vue:211`:

```js
const STATUS = { pass: "Good", fail: "Not Done", issue: "Poor" };
```

Those three strings are the `Safety Task Execution.execution_status` values the server derives the round result from (worst wins — any `Not Done` → Fail, else any `Poor` → Needs Attention, else Pass; `safety_checklist.py:275-277`). The client's `pass|fail|issue` never leaves the browser. A rebuild that renames a verdict must change this map and nothing else.

**`round_date` is the browser's local date**, formatted by hand at `App.vue:229-233` — not the server's `nowdate()`. It doubles as the draft-cache key and as every execution's `execution_date`.

**Realtime.** `frontend/safety/src/realtime.js:4-8` wires `@shared/realtime.js` with `socketGlobal: "safety_socket"`, `roomDoctype: "Safety Round"`, `event: "safety_update"`. The socket config is published by the Jinja shell (`apex/www/safety.html:18-23`) from `apex/www/safety.py:57-61`. The event is emitted by the Safety Round controller on both submit and cancel, `after_commit`, routed to the doctype room (`apex/habitat/doctype/safety_round/safety_round.py:183-195`). The payload is advisory — the portal always refetches `get_due_cadences` and never trusts the message body.

**Never called by this portal:** `get_tasks_for_cadence` and `submit_round` (`safety_checklist.py:71,269`) — see §6.

---

## 3. Who opens it

Login required. `apex/www/safety.py:49` calls `guest_redirect("/safety")` → `redirect_location = "/login?redirect-to=/safety"` + `raise frappe.Redirect` for `frappe.session.user == "Guest"` (`apex/apex_core/utils/portal_bootstrap.py:45-47`).

The role set, quoted from `apex/www/safety.py:31-36`:

```python
SAFETY_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Safety Officer",
}
```

`context.has_safety_role = bool(SAFETY_ROLES & set(frappe.get_roles()))` (`safety.py:54`). Without one of the four the user gets the shared refusal page (`safety.html:31-35` → `apex/templates/includes/portal_denied.html`); the bundle, the CSRF token **and the socket config** are all inside the role branch (`safety.html:11-25`), so a refused user gets no token and opens no socket.

`has_apps_screen_access()` (`safety.py:39-44`) controls **only** the `apex-safety` tile on `/apps`, wired as that tile's `has_permission` at `apex/hooks.py:68-74`. Same `SAFETY_ROLES` test, so the tile matches the door. It gates nothing else.

`apex/www/safety.py:50` additionally calls `render_in_arabic()`, which sets `frappe.local.lang = "ar"` for the rest of the render (`apex/apex_core/utils/portal_language.py:18-20`). That exists so the refusal page's `_()` strings agree with the shell's own `lang="ar" dir="rtl"` (`safety.html:3`) — without it an English sentence lands in an RTL box and the full stop moves to the front of the line.

### Role → capability (the map the merged portal should gate from)

| Role | Opens `/safety` | Reads `Building` (needed by the picker **and** by both APIs) | Reads `Safety Task Catalog` | Submits a round |
|---|---|---|---|---|
| System Manager | yes | yes | yes | yes |
| Accommodation Manager | yes | yes | yes | yes |
| Resident Supervisor | yes | read | read | yes (`submit` on Safety Task Execution) |
| **Safety Officer** | **yes** | **no permission at all** | read | **no `submit`** |

Sources: DocPerms in `apex/habitat/doctype/{building,safety_task_catalog,safety_task_execution,safety_round}/*.json`; the submit gate at `safety_checklist.py:453`; the building gate at `safety_checklist.py:252` and `:457`.

**Safety Officer is admitted at the door and stopped at every desk.** The role is in `SAFETY_ROLES`, so `/safety` opens and the `/apps` tile shows — but `Building` grants no permission to Safety Officer, so `BuildingPicker`'s `frappe.client.get_list` returns nothing and the portal sits on "No buildings available for your account." Even past that, `get_due_cadences` calls `frappe.has_permission("Building","read",doc=building,throw=True)` (`safety_checklist.py:252`) and `submit_due_rounds` requires `submit` on Safety Task Execution (`:453`), which Safety Officer does not hold. This is a known and *intentional* fact of the data model — `safety_round.py:139-141` says so out loud when explaining why that role's alert carries no Building link — but the portal's role set was not written to match it. The merged portal must either drop Safety Officer from the safety section's gate or give the role a maker-only path (it does hold `create` on Safety Round and Safety Task Execution, and `_ratify_executions` at `safety_round.py:103-131` exists precisely to let a checker submit what a Safety Officer recorded).

**Row scoping** is server-side: `Building`, `Safety Round` and `Safety Task Execution` all carry `apex.habitat.permissions.building_scoped_has_permission` / `..._query` (`apex/hooks.py:322-324, 387-389`). A scoped supervisor sees fewer buildings; nothing says "scoped".

---

## 4. What is required of it

*The job, in the words of the person doing it.*

You are the supervisor for a building. Some checks have to happen every day, some every week, some once a month, a quarter or a year. You open the app on your phone, pick your building, and it tells you exactly which of those are still outstanding for the period you are in right now — not a full list you have to sift, only what is not yet done. For each item you get its code, how urgent it is, and, if you tap for it, the instructions for how to check it. You walk the building and tap Pass, Fail, or Issue as you go, and write a note where a note is needed. Your marks stay on the phone while you walk, so you can lock the screen and carry on.

When you are done you press submit once. Everything you marked is filed as an official record — one round per cadence, so a daily and a weekly walked on the same trip become two separate records — and the manager gets an email with the building, the date, the result for each cadence and a list of everything you marked bad. The app tells you plainly whether that email actually went out. From then until the period turns over, that cadence stops being due for that building, for you and for everyone else.

---

## 5. What must survive the rebuild

| Item | Applies? | Exactly what it is |
|---|---|---|
| Server-side role gating | **Yes** | `SAFETY_ROLES` in `safety.py:31-36`, tested at `:54` and again for the `/apps` tile at `:39-44`. Both APIs re-check independently: `frappe.has_permission("Safety Task Catalog","read",throw=True)` (`safety_checklist.py:248`), `frappe.has_permission("Safety Task Execution","submit",throw=True)` (`:453`), `frappe.has_permission("Building","read",doc=building,throw=True)` (`:252,457`). The last of these rejects a supervisor scoped off the building **before** any round is created or any mail is sent. |
| Row scoping | **Yes** | `permission_query_conditions` + `has_permission` on Building, Safety Round, Safety Task Execution (`apex/hooks.py:322-324, 387-389`). `_create_round` inserts with `ignore_permissions=False` explicitly (`safety_checklist.py:380,401`) — the round and its executions are written **as the supervisor**, which is what makes the audit trail meaningful. |
| CSRF propagation | **Yes** | `window.csrf_token` emitted only inside the role branch (`safety.html:14-24`), attached as `X-Frappe-CSRF-Token` by frappe-ui (`node_modules/frappe-ui/src/utils/frappeRequest.js:19-20`). `context.no_cache = 1` (`safety.py:52`). |
| Realtime rooms and teardown | **Yes — this portal's distinguishing capability** | Room: the `Safety Round` doctype room, joined with `socket.emit("doctype_subscribe","Safety Round")` on both `connect` and `reconnect` (`frontend_shared/realtime.js:41-48`) so a dropped connection re-subscribes. Event: `safety_update`, emitted `after_commit` on submit **and** cancel (`safety_round.py:101,181,190-195`). Server-side the socket delivers only to recipients with read permission on the room, so building scope holds without extra filtering (`safety_round.py:186-188`). Teardown: the disposer emits `doctype_unsubscribe`, removes the listeners and disconnects (`frontend_shared/realtime.js:68-76`), and is bound at `App.vue:347-352`. Also survivng: **`socketio: false` is passed to the frappe-ui plugin on purpose** (`frontend_shared/bootstrap.js:18`) — the plugin would open a second, unmanaged socket alongside this one. |
| Offline drafts and queues | **Yes — and this is the half that housing lacks** | `makeCache("apex_safety_draft_")` (`App.vue:179`) writes the whole `ratings` object to `localStorage` on **every** verdict and **every** note keystroke (`App.vue:266,274` → `frontend_shared/makeCache.js:12-17`). The key is `<building>|<local YYYY-MM-DD>` (`App.vue:180`), so drafts are per building **and** per day: walking building B does not clobber building A's marks, and returning to A the same day restores them. Restore happens in exactly one place — `onBuildingSelected` (`App.vue:241`) — so it is triggered by choosing a building, never automatically. Cleared on a successful submit (`App.vue:321`) and on "start another" (`App.vue:257`); **deliberately not** cleared by changing building (`App.vue:245-251`). **What does not survive a reload is the building itself** — `building` is a plain `ref("")` (`App.vue:171`) with no persistence — so after a refresh the supervisor is on the picker and must re-choose the same building on the same date to see their marks again. There is no request queue and no service worker (`frontend/safety/vite.config.js:4` passes no `serviceWorkers`, so `stampServiceWorkers` never runs — `frontend_shared/vite.base.js:59-61`); a submit attempted offline simply fails and the draft is what saves the work. |
| Photo / evidence capture | **Required by the server, absent from the portal — see the defects** | `Safety Task Execution.validate` refuses to submit a Poor / Not Done outcome on a catalog task flagged `evidence_required` unless `evidence_photo` is set (`apex/habitat/doctype/safety_task_execution/safety_task_execution.py:111-153`). The portal shows the flag (`TaskRow.vue:17-20`) and translates the resulting failure into a friendlier message (`App.vue:293-305`, string at `src/i18n.js:104-105`) — but offers no way to attach anything. The contract a rebuild should implement is `frontend_shared/photoFile.js` (accepted types) plus `frontend/driver/src/upload.js` (`readPhotoFile` → data-URL + filename), which is how `/driver` and `/worker` already do it. |
| Routes and deep links | **One route only** | `/safety`. No router, no hash routes, no query parameters, nothing bookmarkable below the portal itself. Also live: the `/apps` tile route `/safety` (`apex/hooks.py:72`). Nothing here is a legacy alias — the `/housing-count` → `/housing#/count` redirect belongs to the housing portal, not this one. A merged portal gains a route where there was none; nothing can break. |
| Language propagation | **Yes, both directions, plus a server-side page language** | Client: `useDocumentLanguage(lang, dir)` (`App.vue:169`) owns `<html lang>` / `<html dir>`; the choice persists in `localStorage["safety_portal_lang"]` (`src/i18n.js:4`). Server: `frontend_shared/call.js:12-16` appends `_lang` to every request; Frappe reads `frappe.form_dict._lang` as its top-priority language source (`frappe/translate.py:46-47`, applied per request at `frappe/auth.py:101`), which is what returns a thrown message such as the evidence refusal in the supervisor's language. Page render: `render_in_arabic()` (`safety.py:50`) fixes the language of the *pre-SPA* shell — see §3. Note the default when nothing is stored is Arabic (`frontend_shared/i18n.js:10`), which matches this shell's `lang="ar"` and **not** housing's `lang="en"`. |

---

## 6. What is deliberately dropped

| Dropped | Evidence |
|---|---|
| `apex.habitat.api.safety_checklist.get_tasks_for_cadence` | Whitelisted at `safety_checklist.py:71`. A repo-wide grep for `get_tasks_for_cadence` (excluding `.ctl/`, `.claude/tests/` and build output) returns **only** its own definition and four docstring mentions inside the same file. No frontend, no Desk page, no other module calls it. It is the single-cadence twin of `get_due_cadences`, which resolves its task set through the same private `_scoped_tasks` helper (`:111-147`), so nothing is lost by dropping the public wrapper. |
| `apex.habitat.api.safety_checklist.submit_round` | Whitelisted at `safety_checklist.py:269`. Same grep: definition plus docstring mentions only. `submit_due_rounds` covers the portal's need and shares the `_create_round` helper (`:343-412`) with it. The one thing `submit_round` can express that `submit_due_rounds` cannot is `is_reinspection=1` (`:328,331`) — a follow-up round past the Safety Round duplicate guard. **That is a real capability with no surface at all**; decide explicitly whether the merged portal needs it before deleting the endpoint. |
| The `online` ref from `makeCache` | `makeCache` returns `{ online, cacheSet, cacheGet }` and attaches `online`/`offline` window listeners (`frontend_shared/makeCache.js:6-10,30`). `App.vue:179` destructures `{ cacheSet, cacheGet }` only. The portal has no offline indicator and no offline branch. |
| Message keys with no consumer (en **and** ar) | `common.none`, `common.error`, `common.submit`, `common.cancel`, `common.note`, `common.back`, `building.current`, `building.start`, `due.rated`, `due.of`, `due.tasksDone`, `due.period`, `due.priority`, `due.someLeft`, `success.done`, `errors.noBuilding`. Grep across `frontend/safety/src` and `frontend/frontend_shared` (excluding `i18n.js`) returns no hit for any. `due.priority` in particular looks live but is not: `TaskRow.vue:103` calls `tEnum("priority", …)`, which resolves the top-level `priority` namespace (`src/i18n.js`), not `due.priority`. |
| Four strings duplicated from the shared fallback | `common.error`, `errors.rateLimited`, `errors.sessionExpired`, `errors.loadError` are byte-identical in `src/i18n.js` and `frontend_shared/sharedMessages.js:3-24`, in both languages, and `createI18n` already falls through (`frontend_shared/i18n.js:28-32`). |

**Not dropped, and not this portal's to delete:** `apex/habitat/page/safety_map` stays. It is the **reference implementation for the job this portal cannot do** — the cross-building safety picture. `/safety` forces a single-building choice and then shows only what is due there; `safety_map` reads Safety Round and its Safety Task Execution rows to answer "which buildings are behind, and where are the findings" (`apex/habitat/api/safety_map.py:15-19,63`). When the merged portal absorbs it, that page is the behaviour to port. The other four Desk pages (`front_desk`, `arrivals_desk`, `transfer_board`, `custody_kiosk`) have no overlap with the safety flow.

---

## Defects found while reading

1. **The mid-flow guard does not prevent the swap it was written to prevent.** `App.vue:334` defines `midFlow = submitted.value !== null || totalRated.value > 0` and `onRealtimeUpdate` (`:335-342`) defers a refetch while it is true. Three holes, all reachable:
   - **Zero verdicts is not mid-flow.** A supervisor who has the checklist open and has typed *notes but no verdict* has `totalRated === 0` (`onNote` writes only `notes`, `:269-274`; `totalRated` counts `verdict` only, `:213-221`), so `midFlow` is false and a `safety_update` fires a refetch. If another supervisor just closed the last due cadence for that building, `due` becomes `[]` and the checklist is replaced by the "nothing due" state under the user, with the typed notes still in `ratings` and in the draft but unreachable. **The guard does not cover the case the defect describes.**
   - **The checklist and the loading state render simultaneously.** The spinner block (`App.vue:44-48`) and the error block (`:49-54`) are siblings *before* the `<Transition>` (`:56`), not part of its `v-if` chain, and frappe-ui sets `loading` true while leaving `data` untouched until the fetch succeeds (`node_modules/frappe-ui/src/resources/resources.js:64` sets `loading`, `:101` is the only assignment to `data`). So during a background refetch the old checklist stays on screen with a spinner above it — and is then replaced.
   - **A deferred refresh can stay deferred forever.** `document.hidden` defers (`:336`) but nothing listens for `visibilitychange`; the only retry is `watch(midFlow, …)` (`:343-345`), which fires on a *change*. If `midFlow` is already false when the tab is hidden, returning to the tab re-triggers nothing and the stale due set persists silently.
   The fix a rebuild needs is not a bigger guard condition: a refresh should never replace a screen the user is on. Offer it ("this building changed — reload?") instead of applying it.
2. **A failed check that requires evidence cannot be submitted at all, and it takes the whole round with it.** `evidence_required` tasks refuse a Poor / Not Done outcome without an `evidence_photo` (`safety_task_execution.py:111-153`); the portal has no upload. Because `submit_due_rounds` wraps every cadence in one outer savepoint and re-raises (`safety_checklist.py:481-504`), **one blocked task discards the entire multi-cadence submit** — a full daily + weekly walk is lost to a single failed fire-door check. The portal's own error string (`src/i18n.js:104-105`) tells the supervisor to "Attach an Evidence Photo", on a screen with no attach control. The only escapes are to change the rating to a pass — which falsifies the record — or to abandon the round. This is the single largest capability gap in the portal.
3. **Safety Officer opens a portal it cannot use.** §3.
4. **Realtime teardown is bound to a component that never unmounts.** `onUnmounted(() => stopRealtime())` (`App.vue:350-352`) sits on the root component; a root unmounts only on `app.unmount()`, which nothing calls. The disposer is correct and must survive, but today it is effectively dead code. In a merged, routed portal the subscription must move to whatever unit actually unmounts, or the unsubscribe will still never run.
5. **The socket gives up after five attempts and says nothing.** `reconnectionAttempts: 5` (`frontend_shared/realtime.js:35`), `connect_error` is swallowed (`:65-66`), and there is no polling fallback. After a long network drop the portal looks live and is not. `frontend_shared/usePoll.js` exists and is unused here.
6. **`round_date` is the browser's local date, the due window is the server's.** `App.vue:229-233` builds `YYYY-MM-DD` from `new Date()`. A device whose clock or timezone straddles midnight relative to the server can submit a round dated to a day the server does not consider current — passing `_cadence_is_due` at fetch time and landing outside `[start, end]` at write time (`safety_checklist.py:200-219`). The draft cache key uses the same local date, so a draft can also become unreachable at a timezone boundary.
7. **Nothing tells the supervisor how much of the round is still unrated at submit time.** `submit_due_rounds` accepts a partial round: `buildResults` skips every task without a verdict (`App.vue:276-291`) and the server records only what it is sent. A supervisor who rated 3 of 40 tasks and submitted has closed the cadence for the whole period (`_cadence_is_due` only asks whether a *submitted* round exists, `safety_checklist.py:210-219`) — the remaining 37 checks are now invisible to everyone until the period turns over. The progress line is shown (`App.vue:122-125`) but is not a gate and carries no warning.
8. **The shipped shell locks zoom.** `apex/www/safety.html:6` sets `maximum-scale=1`, while the dev entry `frontend/safety/index.html` carries an explicit comment that a supervisor reading a 13px task label in a dim corridor must be able to pinch to 200% and omits the lock. The production page contradicts the stated intent and fails WCAG 1.4.4.
9. **A cadence removed by a refresh leaves its ratings behind.** `dueRes.fetch()` never clears `ratings`, and `buildResults` iterates `ratings`, not `due` (`App.vue:276-291`). Any path that both keeps ratings and drops a cadence from `due` will post lines for a cadence that already has a submitted round, which the Safety Round duplicate guard rejects and the outer savepoint turns into a total submit failure. Today the mid-flow guard makes this hard to reach; a rebuild that relaxes the guard, or restores a draft after a refresh, reaches it immediately. Build the payload from `due ∩ ratings`, not from `ratings`.
