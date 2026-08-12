# Unified frontend runtime

Source: [`frontend/apex_portal/`](../../frontend/apex_portal/)

Apex ships one Vue 3 and frappe-ui application for all external portals. The server keeps
each route's authentication and row scope; the client receives only a context, capability
names, and non-secret runtime settings.

```text
frontend/apex_portal/
├── core/       session, permissions, API, realtime, offline and PWA
├── shells/     mobile and operations layouts
├── features/   seven business domains
├── styles/     identity tokens and shared foundation
├── public/     manifests, icons and the generic offline page
└── tooling/    generated-shell and service-worker verification
```

The seven public addresses use one generated Jinja include and one compiled asset tree:

```text
apex/templates/includes/apex_portal_app.html
apex/public/apex_portal/
```

`/masar/` and `/driver/` are the only PWA scopes. Their navigation and API responses are
network-only; only immutable assets and the identity-free offline page may enter cache.

Run from `frontend/`:

```bash
npm ci
npm test
npm run build
```

Commit source, `package-lock.json`, generated Jinja, generated public assets, and both
root-scope service workers together. Component boundaries are recorded beside the source
in [`CONTRACTS.md`](../../frontend/apex_portal/CONTRACTS.md).
