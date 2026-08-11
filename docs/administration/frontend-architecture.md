# Frontend Architecture

Apex uses modern Vue interfaces where a focused mobile or operator experience
is more suitable than a standard Frappe form. The repository separates source,
compiled assets, route delivery, and browser tests because each has a different
deployment role.

## Repository layers

| Path | Responsibility |
|---|---|
| `frontend/` | Vue and Vite source, shared runtime, one dependency manifest, and one lockfile |
| `apex/public/` | Compiled browser bundles served as Frappe assets |
| `apex/www/` | Jinja shells, Python route controllers, and generated root-scope service workers |

This is one delivery pipeline, not four competing implementations. Business
validation and authorization remain in Python controllers and DocTypes; Vue
components present the workflow.

## Approved target architecture

All portal source converges on one capability-driven Vue application. This is
one codebase and one dependency/build boundary, not one large component. Two
shells own device composition; feature modules own business behavior.

```text
frontend/apex_portal/
├── core/
│   ├── session/
│   ├── permissions/
│   ├── realtime/
│   ├── offline/
│   └── router/
├── shells/
│   ├── MobileShell.vue
│   └── OperationsShell.vue
└── features/
    ├── worker/
    ├── driver/
    ├── housing/
    ├── safety/
    ├── fleet-self-service/
    ├── fleet-operations/
    └── transport-supervisor/
```

The server returns allowed sections and actions. The router and navigation use
that capability document for presentation, but it is never the security
boundary: every API continues to enforce Frappe roles, DocPerms, User
Permissions, and row scope. Feature routes load lazily. Mobile and operations
shells may use different offline policies without becoming separate projects.

Existing `/driver`, `/masar`, `/housing`, `/safety`, `/fleet`, `/fleet-os`, and
`/masar-supervisor` links remain compatible during migration. Old source roots
and bundles are removed only after route, permission, offline, accessibility,
test, build, and screenshot parity is demonstrated. This lets every migration
commit remain deployable.

Migration order:

1. Establish `apex_portal` core contracts and both shells.
2. Move Worker and Driver behind `MobileShell`.
3. Move Housing and Safety behind `OperationsShell`.
4. Move fleet self-service, fleet operations, and transport supervision.
5. Replace commodity controls and icons with `frappe-ui` and Lucide; keep only
   Apex-specific SVG assets under `apex/public/icons/`.
6. Repoint the Frappe web shells, prove parity, then delete compatibility code.

## One frontend workspace

`frontend/package.json` owns dependencies and
`frontend/package-lock.json` locks them for every portal. It declares seven
workspace members:

```text
frontend/
  fleet/
  fleet_os/
  frontend_shared/
  housing/
  route_supervisor/
  safety/
  worker/
```

The six portal directories produce bundles. `frontend_shared` provides
the shared runtime, components, design tokens, Vite configuration, and test
harness. Its package manifest declares scripts only; dependencies still belong
to the workspace root.

The source tree also contains `frontend/driver/`. It is consumed by the
`worker` build and is not an npm workspace member or another package. The
worker and driver screens therefore share one compiled bundle while retaining
separate served routes.

## Shared runtime

Portal code imports common behavior through the `@shared` alias:

- `bootstrap.js` creates and mounts the Vue application.
- `call.js` wraps Frappe calls.
- `i18n.js` supplies the shared translation runtime.
- `realtime.js` manages live subscriptions.
- `makeCache.js` supplies offline data caching.
- `components/` contains reusable shells and controls.
- `tokens.css` contains shared design tokens.
- `vite.base.js` creates the common Vite configuration.

Keep portal-specific pages, state, and domain interactions inside their portal.
Move a component into `frontend_shared` only when multiple portals need the
same behavior and API.

## Source shape

Keep each package lean. The six packages share these core files:

```text
<portal>/
  package.json
  vite.config.js
  index.html
  src/
    main.js
    App.vue
    index.css
    i18n.js
```

Add `router.js`, `pages/`, `components/`, `composables/`, or `utils/` only when
the package uses that boundary. Most packages do not need a client router or
every optional directory. Put route-level views in `pages/`, stateful Vue
composition functions in `composables/`, reusable visual pieces in
`components/`, and framework-free helpers in `utils/`.

## Build and serve

Run commands from `frontend/`:

```bash
npm ci
npm test
npm run build
```

`npm test` runs the shared test suite and two worker checks for phone handling
and QR color. It does not test every portal. `npm run build` invokes all six
portal package builds and writes stable bundles under `apex/public/`. Do not
edit generated files by hand. Commit source, lockfile changes, and rebuilt
bundles together.

Frappe serves each interface through a shell and controller in `apex/www/`.
The controller redirects guests or resolves the route-specific identity; the
shell supplies the mount point and approved bootstrap context. Backing APIs
must still enforce document permission and row scope. The worker build also
produces the root-scope service workers served as
`apex/www/driver-sw.min.js` and `apex/www/masar-sw.min.js`; do not edit them by
hand.

See the
[served route reference](../reference/routes-workspaces.md#served-portal-routes)
for current audiences, controllers, and bundle names.

## When to create another portal

Add a screen to an existing portal when it shares the same audience,
authentication path, offline behavior, and deployment lifecycle.

Create another portal package only when a distinct security boundary, device
workflow, service-worker scope, or release lifecycle makes a shared bundle
unsafe or impractical. A new feature alone is not a reason to add another SPA.

Use standard Frappe forms, reports, dashboards, or Desk pages when they already
fit the workflow. The custom frontend layer should solve interaction needs that
native surfaces do not handle well.

## External clients

Third-party frontends do not belong in this workspace unless they ship as part
of Apex. Follow the [Integration Guide](integration.md), especially its rule
that browser code must never contain a Frappe API secret.
