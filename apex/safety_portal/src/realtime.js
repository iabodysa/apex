// Copyright (c) 2026, AFMCO and contributors
// Live updates over Frappe's Socket.IO server: join the "Safety Round" doctype
// room (server gates the join on read permission) and refetch on each
// `safety_update` — a submitted/cancelled Safety Round changes which cadences are
// DUE. The socket wiring/host/teardown lives in the shared factory; this file
// supplies only the safety-specific config. `connectSafetyRealtime(onUpdate)`
// returns a teardown fn; every failure path is swallowed so the portal's own
// fetch still carries it if the socket never connects.
import { createRealtime } from "@shared/realtime.js";

export const connectSafetyRealtime = createRealtime({
  socketGlobal: "safety_socket",
  roomDoctype: "Safety Round",
  event: "safety_update",
});
