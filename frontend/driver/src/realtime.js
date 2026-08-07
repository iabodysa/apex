// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

export const connectDriverRealtime = createRealtime({
  socketGlobal: "driver_socket",
  roomDoctype: "Dispatch Trip",
  event: "driver_trip_update",
  extraEvents: ["boarding_update", "wait_request", "boarding_confirmed", "boarding_unmarked"],
});
