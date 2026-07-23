// Copyright (c) 2026, AFMCO and contributors
// Live board updates over Frappe's Socket.IO server: join the "Salis Vehicle"
// doctype room (server gates the join on read permission) and refetch on each
// `fleet_update`. The socket wiring/host/teardown lives in the shared factory;
// this file supplies only the fleet-specific config. `connectFleetRealtime(onUpdate)`
// returns a teardown fn; every failure path is swallowed so the 30s poll still
// carries the board if the socket never connects.
import { createRealtime } from "@shared/realtime.js";

export const connectFleetRealtime = createRealtime({
  socketGlobal: "fleet_socket",
  roomDoctype: "Salis Vehicle",
  event: "fleet_update",
});
