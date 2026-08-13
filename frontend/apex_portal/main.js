import { createApp } from "vue";
import { FrappeUI } from "frappe-ui";
import App from "./App.vue";
import { createPortalRouter, getPortalContext } from "./core/router.js";
import { parsePortalBootstrap, readPortalDocumentBootstrap } from "./core/session.js";
import { configurePortalApi } from "./core/api.js";
import { createPortalSubscriber } from "./core/realtime.js";
import { registerPortalWorker } from "./core/serviceWorker.js";
import { createPortalPushController } from "./core/pushNotifications.js";
import { createDriverGateway } from "./features/driver/gateway.js";
import { createWorkerGateway } from "./features/worker/gateway.js";
import { portalRoutes } from "./routes.js";
import "./styles/foundation.css";
import "./styles/tokens.css";
import "./styles/frappe-ui-theme.css";

const CONTEXT_TITLES = Object.freeze({
  worker: "مسار",
  driver: "رحلاتي",
  "transport-supervisor": "تشغيل مسار",
  "fleet-self-service": "سلس",
  "fleet-operations": "تشغيل سلس",
  housing: "إدارة السكن",
});

function navigationFrom(router) {
  return router
    .getRoutes()
    .filter((route) => route.meta?.navigation)
    .map((route) =>
      Object.freeze({
        label: route.meta.label,
        icon: route.meta.icon,
        to: route.path,
      }),
    );
}

export async function mountPortal({ source, shell, csrfToken, routes = portalRoutes, target = "#app" } = {}) {
  if (source === undefined && globalThis.document) {
    ({ portal: source, shell, csrfToken } = readPortalDocumentBootstrap(globalThis.document));
  }
  const bootstrap = parsePortalBootstrap(source);
  if (globalThis.window) {
    globalThis.window.apex_portal = bootstrap;
    if (csrfToken !== undefined) globalThis.window.csrf_token = csrfToken;
  }
  const context = getPortalContext(bootstrap.entry);
  const router = createPortalRouter({
    context,
    capabilities: bootstrap.capabilities,
    routes,
    initialRoute: bootstrap.initial_route,
  });
  router.afterEach((to) => {
    if (!globalThis.document) return;
    const page = to.meta?.label || CONTEXT_TITLES[context.id];
    globalThis.document.title = `${page} | أبكس`;
  });
  const application = createApp(App, {
    context,
    title: CONTEXT_TITLES[context.id],
    navigation: navigationFrom(router),
  });
  const call = configurePortalApi();
  const portalPush = ["worker", "driver"].includes(context.id)
    ? createPortalPushController({ entry: context.id, call })
    : null;
  application.provide("portalSubscribe", createPortalSubscriber({ settings: bootstrap }));
  application.provide("portalPush", portalPush);
  application.provide("workerGateway", createWorkerGateway(call));
  application.provide("driverGateway", createDriverGateway(call));
  application.use(FrappeUI, { socketio: false });
  application.use(router);

  const currentHash = globalThis.window?.location.hash.slice(1);
  if (!currentHash || currentHash === "/") await router.replace(bootstrap.initial_route);
  await router.isReady();
  application.mount(target);
  void registerPortalWorker(shell)
    .then((registration) => portalPush?.initialize(registration))
    .catch(() => {});
  return Object.freeze({ application, router, bootstrap, context });
}

if (globalThis.document?.querySelector("#app") && globalThis.document?.querySelector("#apex-portal-bootstrap")) {
  void mountPortal();
}
