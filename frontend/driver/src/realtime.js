// Copyright (c) 2026, afmcoltd
import { createRealtimeHub } from "@shared/portalRealtime.js";
import { realtimeRoom } from "./session.js";

export const DRIVER_EVENTS = [
  "driver_trip_update",
  "boarding_update",
  "boarding_confirmed",
  "boarding_unmarked",
  "boarding_arrived",
  "wait_request",
];

export const useDriverRealtime = createRealtimeHub({
  socketGlobal: "driver_socket",
  events: DRIVER_EVENTS,
  room: realtimeRoom,
});
