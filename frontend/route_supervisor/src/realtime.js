// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

export const connectRouteSupervisorRealtime = createRealtime({
  socketGlobal: "route_supervisor_socket",
  roomDoctype: "Route Plan",
  event: "route_plan_decision",
});
