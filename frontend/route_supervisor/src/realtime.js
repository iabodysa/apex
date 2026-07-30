// Copyright (c) 2026, AFMCO and contributors
// Live updates over Frappe's Socket.IO server: join the "Route Plan" doctype room
// (server gates the join on read permission) and refetch on each
// `route_plan_decision` — published by RoutePlan.set_supervisor_decision, the single
// writer both the approve and the reject endpoint funnel through. The socket
// wiring/host/teardown lives in the shared factory; this file supplies only the
// route-supervisor config. `connectRouteSupervisorRealtime(onUpdate)` returns a
// teardown fn; every failure path is swallowed so the portal's own fetch still
// carries it if the socket never connects.
import { createRealtime } from "@shared/realtime.js";

export const connectRouteSupervisorRealtime = createRealtime({
  socketGlobal: "route_supervisor_socket",
  roomDoctype: "Route Plan",
  event: "route_plan_decision",
});
