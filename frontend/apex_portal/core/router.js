import { createRouter, createWebHashHistory } from "vue-router";
import AccessDenied from "../AccessDenied.vue";
import { can } from "./permissions.js";

export const FEATURE_SLOTS = Object.freeze([
  "worker",
  "driver",
  "housing",
  "safety",
  "fleet-self-service",
  "fleet-operations",
  "transport-supervisor",
]);

function context({ id, publicPaths, features, shell, landing }) {
  return Object.freeze({
    id,
    publicPaths: Object.freeze(publicPaths),
    features: Object.freeze(features),
    shell,
    landing,
  });
}

export const PORTAL_CONTEXTS = Object.freeze({
  worker: context({
    id: "worker", publicPaths: ["/masar/"], features: ["worker"], shell: "mobile", landing: "/home",
  }),
  driver: context({
    id: "driver", publicPaths: ["/driver/"], features: ["driver"], shell: "mobile", landing: "/today",
  }),
  "transport-supervisor": context({
    id: "transport-supervisor", publicPaths: ["/masar-supervisor"], features: ["transport-supervisor"], shell: "operations", landing: "/requests",
  }),
  "fleet-self-service": context({
    id: "fleet-self-service", publicPaths: ["/fleet"], features: ["fleet-self-service"], shell: "mobile", landing: "/vehicle",
  }),
  "fleet-operations": context({
    id: "fleet-operations", publicPaths: ["/fleet-os"], features: ["fleet-operations"], shell: "operations", landing: "/",
  }),
  housing: context({
    id: "housing", publicPaths: ["/housing", "/safety"], features: ["housing", "safety"], shell: "operations", landing: "/overview",
  }),
});

export function getPortalContext(entry) {
  const portalContext = PORTAL_CONTEXTS[entry];
  if (!portalContext) throw new TypeError(`Unknown portal entry: ${entry}`);
  return portalContext;
}

export function createPortalRouter({
  context: activeContext,
  capabilities,
  routes,
  initialRoute = activeContext.landing,
  history,
}) {
  const eligible = routes.filter((route) => activeContext.features.includes(route.feature));
  const deniedPaths = new Set(
    eligible.filter((route) => !can(route.capability, capabilities)).map((route) => route.path),
  );
  const granted = eligible.filter((route) => can(route.capability, capabilities));
  const landing = granted.some((route) => route.path === initialRoute)
    ? initialRoute
    : granted.some((route) => route.path === activeContext.landing)
      ? activeContext.landing
    : "/access-denied";

  return createRouter({
    history: history ?? createWebHashHistory(),
    routes: [
      ...granted,
      { path: "/access-denied", name: "access-denied", component: AccessDenied },
      {
        path: "/:pathMatch(.*)*",
        name: "portal-fallback",
        redirect: (to) => deniedPaths.has(to.path)
          ? { path: "/access-denied", query: { from: to.fullPath } }
          : landing,
      },
    ],
  });
}
