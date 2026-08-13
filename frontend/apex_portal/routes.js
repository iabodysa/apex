import { driverRoutes } from "./features/driver/routes.js";
import { createFleetOperationsRoutes } from "./features/fleet-operations/routes.js";
import { createFleetSelfRoutes } from "./features/fleet-self-service/routes.js";
import { housingRoutes } from "./features/housing/routes.js";
import { safetyRoutes } from "./features/safety/routes.js";
import { supervisorRedirects, supervisorRoutes } from "./features/transport-supervisor/routes.js";
import { workerRoutes } from "./features/worker/routes.js";

export const portalRoutes = Object.freeze([
  ...workerRoutes,
  ...driverRoutes,
  ...housingRoutes,
  ...safetyRoutes,
  ...createFleetSelfRoutes(),
  ...createFleetOperationsRoutes(),
  ...supervisorRoutes,
  ...supervisorRedirects.map((route) => Object.freeze({
    ...route,
    feature: "transport-supervisor",
    capability: "transport.assignment.read",
  })),
]);
