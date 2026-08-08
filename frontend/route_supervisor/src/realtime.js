// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

/* The global name has to match what masar-supervisor.html publishes; when the two drifted the
   factory saw an empty site and returned a no-op, so the room was never joined. */
export const connectRouteSupervisorRealtime = createRealtime({
  socketGlobal: "route_supervisor_socket",
  roomDoctype: "Route Plan",
  event: "route_plan_decision",
});
