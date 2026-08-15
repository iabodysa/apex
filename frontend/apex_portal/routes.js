import { driverRoutes } from "./features/driver/routes.js";
import { createFleetOperationsRoutes } from "./features/fleet-operations/routes.js";
import { createFleetSelfRoutes } from "./features/fleet-self-service/routes.js";
import { housingRoutes } from "./features/housing/routes.js";
import { safetyRoutes } from "./features/safety/routes.js";
import { supervisorRedirects, supervisorRoutes } from "./features/transport-supervisor/routes.js";
import { workerRoutes } from "./features/worker/routes.js";

/**
 * Copies a route's `feature` into its `meta`, which is the only carrier that survives resolution.
 *
 * `createPortalRouter` reads `feature` off the raw record to pick a context's routes, but
 * vue-router rebuilds every record through `normalizeRouteRecord`
 * (node_modules/vue-router/dist/vue-router.mjs:778) whose field list is closed — a custom
 * top-level key is dropped, and only `meta` reaches the resolved location a navigation guard
 * sees. The document title is composed after resolution, so it has to read the feature there.
 *
 * @param {object} route a portal route record carrying a top-level `feature`
 * @returns {object} the same record with `feature` mirrored into a frozen `meta`
 */
const carryFeatureIntoMeta = (route) =>
  Object.freeze({
    ...route,
    meta: Object.freeze({ ...route.meta, feature: route.feature }),
  });

export const portalRoutes = Object.freeze([
  ...workerRoutes,
  ...driverRoutes,
  ...housingRoutes,
  ...safetyRoutes,
  ...createFleetSelfRoutes(),
  ...createFleetOperationsRoutes(),
  ...supervisorRoutes,
  ...supervisorRedirects.map((route) => ({
    ...route,
    feature: "transport-supervisor",
    capability: "transport.assignment.read",
  })),
].map(carryFeatureIntoMeta));
