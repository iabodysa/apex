// Copyright (c) 2026, afmcoltd
import { Dialogs, FrappeUI } from "frappe-ui";
import { createApp, h } from "vue";
import { configureApi } from "./call.js";

/* `confirmDialog()` pushes onto a module-level list and renders nothing by itself — `Dialogs`
   is the surface that draws that list, and it has to be mounted exactly once. Mounting it here
   rather than inside each portal's own root means a portal cannot forget it, and a confirm
   raised from anywhere in any portal appears. Its own root element is deliberate: the list is
   module state, so this host sees every dialog without sharing the portal's component tree. */
function mountDialogHost() {
  const host = document.createElement("div");
  host.setAttribute("data-portal-dialogs", "");
  document.body.appendChild(host);
  createApp({ render: () => h(Dialogs) }).mount(host);
}

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
  mountDialogHost();
  return app;
}
