// Copyright (c) 2026, afmcoltd
import { FrappeUI } from "frappe-ui";
import { createApp } from "vue";
import { configureApi } from "./call.js";

/* One mount path for every portal, so the library is initialised the same way in all of them.
 *
 * `configureApi` first: it registers the resourceFetcher that carries the interface language
 * on every request, and the resources plugin installed below hands its resources to that
 * fetcher — installing the plugin first would leave the first requests without the language.
 *
 * `socketio: false` is deliberate and must stay. The plugin would open its own socket, and
 * the portals already subscribe through realtime.js with their own rooms and teardown; two
 * sockets would mean two subscriptions and one of them unmanaged. */
export function bootstrapPortal({ App, router, setup }) {
  configureApi();
  const app = createApp(App);
  app.use(FrappeUI, { socketio: false });
  if (router) app.use(router);
  if (setup) setup(app);
  app.mount("#app");
  return app;
}
