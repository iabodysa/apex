// Copyright (c) 2026, afmcoltd
import { createApp } from "vue";
import { configureApi } from "./call.js";

export function bootstrapPortal({ App, router, setup }) {
  configureApi();
  const app = createApp(App);
  if (router) app.use(router);
  if (setup) setup(app);
  app.mount("#app");
  return app;
}
