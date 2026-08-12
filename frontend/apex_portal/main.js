import { createApp } from "vue";
import { FrappeUI } from "frappe-ui";
import App from "./App.vue";
import { createPortalRouter, getPortalContext } from "./core/router.js";
import { parsePortalBootstrap } from "./core/session.js";
import "./styles/foundation.css";

const CONTEXT_TITLES = Object.freeze({
  worker: "مسار",
  driver: "رحلاتي",
  "transport-supervisor": "تشغيل مسار",
  "fleet-self-service": "سلس",
  "fleet-operations": "تشغيل سلس",
  housing: "إدارة السكن",
});

function navigationFrom(router) {
  return router.getRoutes()
    .filter((route) => route.meta?.navigation)
    .map((route) => Object.freeze({
      label: route.meta.label,
      icon: route.meta.icon,
      to: route.path,
    }));
}

export async function mountPortal({
  source = globalThis.window?.apex_portal,
  routes = [],
  target = "#app",
} = {}) {
  const bootstrap = parsePortalBootstrap(source);
  const context = getPortalContext(bootstrap.entry);
  const router = createPortalRouter({
    context,
    capabilities: bootstrap.capabilities,
    routes,
  });
  const application = createApp(App, {
    context,
    title: CONTEXT_TITLES[context.id],
    navigation: navigationFrom(router),
  });
  application.use(FrappeUI, { socketio: false });
  application.use(router);

  const currentHash = globalThis.window?.location.hash.slice(1);
  if (!currentHash || currentHash === "/") await router.replace(bootstrap.initial_route);
  await router.isReady();
  application.mount(target);
  return Object.freeze({ application, router, bootstrap, context });
}

if (globalThis.document?.querySelector("#app") && globalThis.window?.apex_portal) {
  void mountPortal();
}
