// Copyright (c) 2026, AFMCO and contributors
// Live trip updates over Frappe's Socket.IO server: join the "Dispatch Trip"
// doctype room (the server gates the join on read permission, so a driver only
// receives pushes for trips they can read) and refetch on each
// `driver_trip_update`. Boarding-flow events (salis.api.boarding_flow) ride the
// SAME room so the manifest panel repaints on a worker's claim/wait/boarding
// change without a manual refresh; each payload carries dispatch_trip. The socket
// wiring/host/teardown lives in the shared factory; this file supplies only the
// driver-specific config. `connectDriverRealtime(onUpdate, onBoarding)` returns a
// teardown fn; every failure path is swallowed so the existing fetch /
// pull-to-refresh still carries the trips if the socket never connects.
import { createRealtime } from "@shared/realtime.js";

export const connectDriverRealtime = createRealtime({
  socketGlobal: "driver_socket",
  roomDoctype: "Dispatch Trip",
  event: "driver_trip_update",
  extraEvents: ["boarding_update", "wait_request", "boarding_confirmed", "boarding_unmarked"],
});
