# Frontend architecture

Apex uses one Vue 3 and frappe-ui application for the mobile and tablet workflows that do
not fit a standard Frappe form. Frappe remains responsible for identity, permissions,
business validation, documents, workflows, and persistence.

## Delivery layers

| Path | Responsibility |
|---|---|
| `frontend/apex_portal/` | Authored Vue source, tests, PWA inputs, and build tooling |
| `apex/public/apex_portal/` | Generated browser assets served by Frappe |
| `apex/templates/includes/apex_portal_app.html` | Generated Jinja application shell |
| `apex/www/` | Seven thin route controllers and two generated root-scope workers |

The separation follows Frappe delivery requirements; it is not four frontend
implementations. Never edit generated assets or the generated Jinja include by hand.

## Application tree

```text
frontend/apex_portal/
├── core/
│   ├── api.js
│   ├── session.js
│   ├── permissions.js
│   ├── router.js
│   ├── realtime.js
│   ├── offline.js
│   └── serviceWorker.js
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

`MobileShell` serves workers, drivers, and fleet representatives on phones.
`OperationsShell` serves housing, safety, fleet, and transport supervisors on tablets.
Features own domain behavior; shared folders contain only behavior with multiple real
consumers.

## Security boundary

Each Python controller authenticates first and then creates the strict bootstrap object.
It contains capability names and an opaque draft namespace, not user names, record ids,
tokens, or cookies. The router uses capabilities to shape navigation, but every API repeats
DocPerm, User Permission, project, building, employee, or token scope on the server.

The seven routes are `/masar/`, `/driver/`, `/masar-supervisor`, `/fleet`, `/fleet-os`,
`/housing`, and `/safety`. `/housing-count` remains a temporary redirect to
`/housing#/count`.

## Build and verification

`frontend/package.json` declares one workspace and `frontend/package-lock.json` is the only
lockfile.

```bash
cd frontend
npm ci
npm test
npm run build
```

The build writes one asset tree, generates the shared Jinja include, and reconstructs both
PWA workers. CI repeats the build and rejects any generated-file drift.

Use native Frappe pages, forms, reports, and dashboards when they fit the work. Add a portal
feature only for a genuinely different field interaction; a new feature is not a reason to
create another SPA.
