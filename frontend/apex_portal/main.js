import { createApp } from "vue";
import { FrappeUI } from "frappe-ui";
import App from "./App.vue";
import { createPortalRouter, getPortalContext } from "./core/router.js";
import { parsePortalBootstrap, readPortalDocumentBootstrap } from "./core/session.js";
import { configurePortalApi } from "./core/api.js";
import { createDocSubscriber, createDoctypeSubscriber, createPortalSubscriber } from "./core/realtime.js";
import { createPortalUpdateController, registerPortalWorker } from "./core/serviceWorker.js";
import { __ } from "./core/i18n.js";
import { createPortalPushController } from "./core/pushNotifications.js";
import { createDraftStore } from "./core/offline.js";
import { createDriverGateway } from "./features/driver/gateway.js";
import { createWorkerGateway } from "./features/worker/gateway.js";
import { portalRoutes } from "./routes.js";
import "./styles/foundation.css";
import "./styles/tokens.css";
import "./styles/frappe-ui-theme.css";

const CONTEXT_TITLES = Object.freeze({
  worker: __("Masar"),
  driver: __("My trips"),
  "transport-supervisor": __("Masar operations"),
  "fleet-self-service": __("Salis"),
  "fleet-operations": __("Salis operations"),
  housing: __("Housing management"),
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
        group: route.meta.group,
      }),
    );
}

export async function mountPortal({ source, shell, csrfToken, routes = portalRoutes, target = "#app", history } = {}) {
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
    history,
  });
  router.afterEach((to) => {
    if (!globalThis.document) return;
    // Six labels — العهد, السكن, اليوم among them — are destinations in more than one persona, so
    // the label alone leaves three tabs reading "العهد | أبكس". The feature is what tells them
    // apart, and it is read from `meta` because that is the only place vue-router carries a
    // custom record key through to a resolved location; see routes.js.
    const page = to.meta?.label;
    const persona = CONTEXT_TITLES[to.meta?.feature] || CONTEXT_TITLES[context.id];
    const brand = __("Apex");
    globalThis.document.title = page && page !== persona
      ? `${page} · ${persona} | ${brand}`
      : `${persona} | ${brand}`;
  });
  const application = createApp(App, {
    context,
    title: CONTEXT_TITLES[context.id],
    navigation: navigationFrom(router),
  });
  const call = configurePortalApi();
  const portalDrafts = globalThis.window?.localStorage
    ? createDraftStore({
        storage: globalThis.window.localStorage,
        site: bootstrap.site_name,
        entry: context.id,
        subjectScope: bootstrap.subject_scope,
      })
    : null;
  portalDrafts?.activate();
  const portalPush = ["worker", "driver"].includes(context.id)
    ? createPortalPushController({ entry: context.id, call })
    : null;
  application.provide("portalSubscribe", createPortalSubscriber({ settings: bootstrap }));
  application.provide("portalBuildingSubscribe", createDocSubscriber({ settings: bootstrap, doctype: "Building" }));
  application.provide("portalDoctypeSubscribe", createDoctypeSubscriber({ settings: bootstrap }));
  application.provide("portalPush", portalPush);
  application.provide("workerGateway", createWorkerGateway(call));
  application.provide("driverGateway", createDriverGateway(call));
  application.provide("portalDrafts", portalDrafts);
  const portalUpdate = createPortalUpdateController();
  application.provide("portalUpdate", portalUpdate);
  application.provide(
    "portalBrand",
    Object.freeze({ logo: (shell?.show_brand !== false && shell?.brand_logo) || "" }),
  );
  application.use(FrappeUI, { socketio: false });
  application.use(router);

  const currentHash = globalThis.window?.location.hash.slice(1);
  if (!currentHash || currentHash === "/") await router.replace(bootstrap.initial_route);
  await router.isReady();
  application.mount(target);
  void registerPortalWorker(shell)
    .then((registration) => {
      portalUpdate.attach(registration);
      return portalPush?.initialize(registration);
    })
    .catch(() => {});
  return Object.freeze({ application, router, bootstrap, context });
}

if (globalThis.document?.querySelector("#app") && globalThis.document?.querySelector("#apex-portal-bootstrap")) {
  void mountPortal();
}
