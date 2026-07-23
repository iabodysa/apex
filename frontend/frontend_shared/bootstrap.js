// Copyright (c) 2026, AFMCO and contributors
// [#shared-bootstrap]
// bootstrapPortal(config) is the one SPA boot sequence shared by every *_portal
// main.js. Each portal repeated the same four steps — wire frappe-ui's
// resourceFetcher (configureApi), createApp(App), optionally app.use(router),
// mount("#app"). This holds that once so a portal's main.js is a single call;
// the portal passes only its root App, its optional router, and an optional
// `setup(app)` hook for the rare pre-mount side-effect (driver's initPwa).
import { createApp } from "vue";
import { configureApi } from "./call.js";

// bootstrapPortal({ App, router?, setup? }) -> the mounted app instance.
//   App    — the root component (required)
//   router — the vue-router instance (omit for the router-less single-view portals)
//   setup  — optional (app) => void run after createApp, before mount, for a
//            pre-mount side-effect that must fire on boot (e.g. initPwa)
export function bootstrapPortal({ App, router, setup }) {
  // Sign every createResource() request with window.csrf_token (shared layer).
  configureApi();
  const app = createApp(App);
  if (router) app.use(router);
  if (setup) setup(app);
  app.mount("#app");
  return app;
}
