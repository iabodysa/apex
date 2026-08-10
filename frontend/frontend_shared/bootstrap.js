// Copyright (c) 2026, afmcoltd
import { Dialogs, FrappeUI } from "frappe-ui";
import { createApp, h } from "vue";
import { configureApi } from "./call.js";

function mountDialogHost() {
  const host = document.createElement("div");
  host.setAttribute("data-portal-dialogs", "");
  document.body.appendChild(host);
  createApp({ render: () => h(Dialogs) }).mount(host);
}

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
