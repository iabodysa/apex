# frontend_shared

Code shared by every `*_portal` SPA (fleet, fleet_os, worker+driver, safety,
housing, route_supervisor). These portals are Vite + Vue 3 apps that build to
committed bundles under `apex/public/<portal>/` and are served by the
`www/<portal>.html` Jinja shells. `frontend_shared/` holds the parts that must
not drift between portals.

## One workspace, one manifest, one lockfile

`frontend/` is a single npm workspace. `frontend/package.json` is the **only**
manifest that declares dependencies and `frontend/package-lock.json` the **only**
lockfile; every portal package.json carries just its name and its `dev`/`build`
scripts. A framework version therefore cannot drift between portals — the
condition the retired `pins.json` + `override-pins`/`dep-pins` CI loops used to
police by hand.

```
frontend/
  package.json          # every dependency + the security `overrides`  <- the one manifest
  package-lock.json     # the one lockfile
  frontend_shared/      # shared runtime + components + vitest harness (no bundle)
  fleet/ fleet_os/ housing/ route_supervisor/ safety/ worker/   # the six portals
  driver/               # driver screens, no manifest — built INTO worker_portal
```

Build and test from `frontend/`:

```bash
npm ci                       # install the whole workspace from the frozen lockfile
npm run build                # build every portal bundle
npm run build -w fleet_portal   # or just one
npm test                     # frontend_shared vitest + the node unit tests
```

Bumping a dependency is a one-file edit in `frontend/package.json`, then
`npm install` (refreshes the lockfile) and `npm run build` (refreshes every
committed bundle — `bundle-guard` fails otherwise).

`driver/` has no package.json, vite.config.js or output dir on purpose: the
driver and worker screens ship as ONE bundle whose host is `worker`
(`worker/src/main.js` lazily imports `../../driver/src/*`), serving `/masar`
for holder_type Worker and `/driver` for holder_type Driver.

## What lives here

| File | Role |
| --- | --- |
| `vite.base.js` | `createPortalConfig({ dirname, name, serviceWorkers? })` — the single Vite config factory. Every `<portal>/vite.config.js` is a <=15-line call to it. Defines the frappe-ui + vue plugins, the dev proxy, the `@`/`@shared` aliases, the vue/frappe-ui dedupe, the stable un-hashed output names, and the one `stampServiceWorkers` plugin (opt-in via `serviceWorkers`). |
| `i18n.js` | Shared translation runtime. |
| `call.js` | Shared Frappe API call helper. |
| `bootstrap.js` | `bootstrapPortal({ App, router?, setup? })` — the one SPA boot sequence (configureApi + createApp + optional router + optional pre-mount `setup(app)` + mount). Every `<portal>/src/main.js` is a single call to it. |
| `realtime.js` | `createRealtime({ socketGlobal, roomDoctype, event, extraEvents? })` — the Frappe Socket.IO subscription factory (host/join/refetch/teardown, every failure path swallowed). Used by the live portals (fleet, safety, driver); each supplies only its socket-config global, room doctype, event, and optional same-room extra events. Its `socket.io-client` import resolves via the factory's `dedupe`. |
| `makeCache.js` | Shared offline/data cache factory. |
| `components/` | Shared presentational `.vue` components imported via `@shared/components/*` (e.g. `Brand.vue` — the Apex inline-SVG mark, self-contained and token-driven), the `LangToggle` header control and the three page shells (`FleetPageShell`, `MobileConsoleShell`, `TabletSupervisorShell`). |
| `tokens.css` | Shared Apex design tokens (CSS custom properties), plus the single `:focus-visible` ring and the `prefers-reduced-motion` duration collapse. |
| `photoFile.js` | The client half of the photo contract: the accepted set (JPEG/PNG/WebP) written once, so the three pickers in two portals cannot drift from the server's byte check in `apex/salis/api/driver_portal/images.py`. |

## Arabic has one home, and the dictionaries are a declared exception

`apex/translations/ar.csv` is the **only** home for Arabic in the tracked tree. No
label, Select option, `_()` source string, workspace name, comment, test fixture,
entry-HTML `<title>` or doc line carries an Arabic literal.

The **one declared exception** is the portal dictionaries — `frontend/*/src/i18n.js`
— and it is **time-boxed, not a second home**: they stay only until they are
GENERATED from `ar.csv` at build time. They exist because these portals ship
deliberately WITHOUT Frappe's JS bundle so they run offline, and `window.__` reads
`frappe._messages`, which arrives with that bundle. So the runtime lookup has to be
local; the source string does not. Until the generator lands, an Arabic string added
to a dictionary must be **verbatim from `ar.csv`** — copy the value, do not compose a
new one.

Sweep (run from the repo root; needs `rg`):

```bash
git ls-files -z | xargs -0 rg -l '[\x{0600}-\x{06FF}]' \
  | grep -v '^apex/public/' \
  | grep -v 'apex/translations/ar.csv' \
  | grep -v 'src/i18n.js$' \
  | grep -v 'frontend/worker/public/'
```

The four exclusions are the generated bundles, the one home, the declared exception,
and binary assets (a `.woff2` carries Arabic glyph data, a `.png` its icon text).
What the sweep is allowed to return is **the print templates and nothing else**: ten
bilingual sheets (`apex/{habitat,salis}/print_format/*/*.html`, 138 Arabic lines).
Accepted, not deferred — each prints English and Arabic side by side in its own
markup, so `default_print_language: "en"` is load-bearing there, and
`apex/habitat/print_format/test_print_format_language_pinning.py` fails the build if
a template's Arabic and its pin disagree. Three `test_*.py` files also match: their
only hit is the literal Unicode RANGE (U+0600-U+06FF) inside the scanners' own
regex — the guard's alphabet, not content. Write ranges escaped, never as literal
characters, or the rule text trips its own sweep.

## frappe-ui is the toolkit, not a dependency to ration — owner rule, 2026-08-03

Use `frappe-ui` as it is, with its features. Its components, its calls, its styles and its
shapes are what a portal is built from; it is a Vue library with an ordered component tree,
and that tree is the structure these portals are meant to have.

The rule in one line: **reach for the library's component first, and hand-write only what it
does not have.**

- Controls come from `frappe-ui` — Button, Dialog, Select, Autocomplete, FormControl,
  ErrorMessage, Badge, Avatar, ListView, Tabs, Switch, Checkbox, TextInput, Textarea,
  DatePicker, Progress, Alert, Tooltip, Dropdown, Breadcrumbs, `toast`, and the chart
  components. The workspace already resolves the package and `vite.base.js` already
  registers its plugin, so there is nothing to set up.
- Data comes from `createResource` / `createListResource` through `call.js`, which signs
  every request with `frappeRequest`. That was already the practice.
- The Apex tokens still decide colour, spacing and tap size. Pass them into a component's
  class or slot rather than restyling it from scratch, and never fork a component to change
  its look.
- What stays local is what the library has no answer for: the three page shells, `Brand`,
  `LangToggle`, `BuildingPicker`, `EmptyState`, and the offline layer
  (`makeCache`, the service worker, `usePoll`).
- A hand-rolled control that duplicates a library component is a defect, not a preference.
  If you write one, the report says which library component you searched for and why it did
  not fit.

An earlier decision here said the opposite — keep frappe-ui for data, do not adopt its
components — on the grounds that its Tailwind styling would fragment the token system. The
owner overruled it: the library's own features are the point, and its look is configured
through the tokens rather than avoided.

## Tailwind is opt-in per BUILD UNIT

| Build unit (has `vite.config.js`) | `tailwind.config.js` | emits `@tailwind` |
| --- | --- | --- |
| `housing` `safety` `worker` | yes | yes |
| `fleet` `fleet_os` `route_supervisor` | no | no |

Both greps return the same set:

```bash
ls frontend/*/tailwind.config.js                         # housing safety worker
rg -l '@tailwind|@apply' frontend/*/src/**.css           # driver housing safety worker
```

`driver/` is the one name that appears in the second list and not the first, and that
is correct rather than drift: `driver/` is **not a build unit** — it has no
`package.json`, `vite.config.js` or output dir, and its screens are compiled INTO
`worker_portal` (see the layout above). `worker/tailwind.config.js` therefore owns
driver's CSS, and its `content` globs scan `../driver/src/**` so driver-only utility
classes are not purged. A `driver/tailwind.config.js` would never be read, because
Tailwind resolves its config from the Vite root, which is always `worker/`.

Why Tailwind stays rather than being removed everywhere: the four consumers use
utility classes throughout their templates, so removing it is a rewrite of four
portals' markup, not a config change. Why it is not added to the other three: they
carry hand-written CSS and reference no utility class, so a config there would ship
dead CSS. `tailwindcss` / `postcss` / `autoprefixer` stay in `frontend/package.json`
(the one manifest) because three build units use them.

### The token layer is the whole appearance contract

A portal `@import "@shared/tokens.css"` and declares **no palette of its own**.
`tokens.css` ships one light palette; tenant branding may override only the accent.
`__tests__/tokens.test.mjs` fails on an undeclared `var(--x)`, a theme branch, or a
revert of a contrast-corrected value.

Two shared conventions consume it:

- `--tap-lg / --tap-md / --tap-min` (52 / 48 / 44px) — nothing interactive goes
  below `--tap-min`.
- `data-motion="loop"` — mark a genuine busy indicator with it and reduced motion
  slows it to 2.4s instead of freezing it mid-turn. Everything else collapses.

Import from a portal with the `@shared` alias, e.g. `import { call } from "@shared/call.js"`.
`frontend_shared/` has no `node_modules` of its own; bare imports (`vue`,
`frappe-ui`) resolve to the workspace-hoisted copy at `frontend/node_modules`
via the factory's `dedupe`.

## Canonical portal `src/` skeleton

Every portal's `src/` follows the same shape so a reader can navigate any portal
by muscle memory:

```
<portal>/
  vite.config.js        # <=15-line createPortalConfig() call
  package.json          # name + dev/build scripts ONLY — deps live in frontend/package.json
  index.html            # Vite entry (dev); prod shell is www/<portal>.html
  src/
    main.js             # app bootstrap (createApp, router, mount) — root only
    App.vue             # root component — root only
    router.js           # route table — root only
    index.css           # global styles / token import — root only
    i18n.js             # portal i18n config (wraps @shared/i18n) — root only
    pwa.js              # service-worker registration glue — root only (PWA portals)
    pages/              # one file per route (route-level views)
    components/         # reusable presentational components
    composables/        # use*.js — stateful Vue composition functions
    utils/              # pure, framework-free helpers (dates, phone, cache, qr, tokens)
```

Rule: `src/` root holds only the app-entry/config files above. Every `use*.js`
belongs in `composables/`; every pure helper belongs in `utils/`. No loose
helper modules at the `src/` root.

## Serve layer (`apex/www/`)

- `<portal>.html` — Jinja shell (csrf boot + SPA mount). The per-tenant accent
  override is a shared partial: `{% include "apex/templates/includes/portal_accent.html" %}`,
  included by exactly the shells whose `get_context` calls
  `apply_portal_appearance` (driver, masar, housing, safety) so its security
  rationale lives in exactly one place and no shell renders a variable it was
  never given.
- `driver-sw.min.js` / `masar-sw.min.js` — the two PWA service workers, served
  from root so their scope covers `/driver` and `/masar`. Their `BUILD` marker is
  stamped with the bundle hash by the factory's `stampServiceWorkers` plugin.

## CI

- `.github/workflows/portal-bundles.yml`
  - `bundle-guard` — installs the workspace from the frozen lockfile, rebuilds
    each portal and fails if the committed `apex/public/<portal>/` (and stamped
    `www` SW) is stale. Rebuild and commit the bundle after any portal `src/`,
    `frontend_shared/` or dependency change.
  - `manifest-ownership` — fails if a portal reintroduces its own
    dependencies/overrides or a second lockfile, or if the root manifest loses
    the `dompurify` / `ws` security overrides.
- `.github/workflows/portal-tests.yml` `shared-components` — vitest for
  `@shared/components/*`, run from the workspace.
- `apex/tests/test_release_hygiene.py::TestFrontendWorkspaceOwnership` asserts the
  same single-manifest/single-lockfile invariant from the Python suite.
