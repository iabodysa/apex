import { START_LOCATION, createRouter, createRouterMatcher, createWebHashHistory } from "vue-router";
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
    id: "housing", publicPaths: ["/housing", "/safety"], features: ["housing", "safety"], shell: "operations", landing: "/today",
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
  const granted = eligible.filter((route) => can(route.capability, capabilities));
  // A denied route is held as a pattern, not as a string. "/beds/:bed" never equals "/beds/BED-1",
  // so a Set of raw paths recognised only the parameterless refusals and let every deep link into a
  // record fall through to the landing list — the screen that looks like the request succeeded.
  // vue-router's own matcher is what tells a pattern from a path, so the refusal borrows it rather
  // than growing a second path grammar beside the one the router already runs.
  const deniedMatcher = createRouterMatcher(
    eligible.filter((route) => !can(route.capability, capabilities)),
    {},
  );
  const isDenied = (path) => deniedMatcher.resolve({ path }, START_LOCATION).matched.length > 0;
  const landing = granted.some((route) => route.path === initialRoute)
    ? initialRoute
    : granted.some((route) => route.path === activeContext.landing)
      ? activeContext.landing
    : "/access-denied";

  return createRouter({
    history: history ?? createWebHashHistory(),
    routes: [
      ...granted,
      {
        path: "/access-denied",
        name: "access-denied",
        component: AccessDenied,
        // Without a label the refusal inherits the persona's bare title, so a denied deep link
        // and the landing screen are the same entry in history and in a shared tab.
        meta: { navigation: false, label: "لا تملك صلاحية" },
      },
      {
        path: "/:pathMatch(.*)*",
        name: "portal-fallback",
        redirect: (to) => (isDenied(to.path)
          ? { path: "/access-denied", query: { from: to.fullPath } }
          : landing),
      },
    ],
  });
}
