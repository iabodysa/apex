# frontend_shared

Code shared by every `*_portal` SPA (fleet, worker, driver, safety, housing).
These portals are standalone Vite + Vue 3 apps that build to committed bundles
under `apex_habitat/public/<portal>/` and are served by the `www/<portal>.html`
Jinja shells. `frontend_shared/` holds the parts that must not drift between
portals.

## What lives here

| File | Role |
| --- | --- |
| `vite.base.js` | `createPortalConfig({ dirname, name, sw? })` — the single Vite config factory. Every `<portal>/vite.config.js` is a <=15-line call to it. Defines the frappe-ui + vue plugins, the dev proxy, the `@`/`@shared` aliases, the vue/frappe-ui dedupe, the stable un-hashed output names, and the one `stampServiceWorker` plugin (opt-in via `sw`). |
| `i18n.js` | Shared translation runtime. |
| `call.js` | Shared Frappe API call helper. |
| `bootstrap.js` | `bootstrapPortal({ App, router?, setup? })` — the one SPA boot sequence (configureApi + createApp + optional router + optional pre-mount `setup(app)` + mount). Every `<portal>/src/main.js` is a single call to it. |
| `realtime.js` | `createRealtime({ socketGlobal, roomDoctype, event, extraEvents? })` — the Frappe Socket.IO subscription factory (host/join/refetch/teardown, every failure path swallowed). Used by the live portals (fleet, safety, driver); each supplies only its socket-config global, room doctype, event, and optional same-room extra events. Its `socket.io-client` import resolves via the factory's `dedupe`. |
| `makeCache.js` | Shared offline/data cache factory. |
| `components/` | Shared presentational `.vue` components imported via `@shared/components/*` (e.g. `Brand.vue` — the AFMCO inline-SVG emblem/supergraphic, self-contained, token-driven). |
| `tokens.css` | Shared design tokens (CSS custom properties). |
| `pins.json` | Canonical `overrides` (dompurify, ws) that every portal `package.json` must mirror. The `portal-bundles` CI job fails on drift. |

Import from a portal with the `@shared` alias, e.g. `import { call } from "@shared/call.js"`.
`frontend_shared/` has no `node_modules`; bare imports (`vue`, `frappe-ui`) resolve
to the importing portal's copy via the factory's `dedupe`.

## Canonical portal `src/` skeleton

Every portal's `src/` follows the same shape so a reader can navigate any portal
by muscle memory:

```
<portal>/
  vite.config.js        # <=15-line createPortalConfig() call
  package.json          # deps + the shared `overrides` (see pins.json)
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

## Serve layer (`apex_habitat/www/`)

- `<portal>.html` — Jinja shell (csrf boot + SPA mount). The per-tenant accent
  override is a shared partial: `{% include "apex_habitat/templates/includes/portal_accent.html" %}`
  so its security rationale lives in exactly one place.
- `driver-sw.min.js` / `masar-sw.min.js` — the two PWA service workers, served
  from root so their scope covers `/driver` and `/masar`. Their `BUILD` marker is
  stamped with the bundle hash by the factory's `stampServiceWorker` plugin.

## CI

- `.github/workflows/portal-bundles.yml`
  - `bundle-guard` — rebuilds each portal from its frozen lockfile and fails if
    the committed `public/<portal>/` (and stamped `www` SW) is stale. Rebuild and
    commit the bundle after any portal `src/` or `frontend_shared/` change.
  - `override-pins` — fails if any portal's `package.json` `overrides` drift from
    `pins.json`.
- `.github/workflows/test.yml` `spa-lockfiles` — `npm ci` per portal keeps the
  frozen lockfiles honest.
