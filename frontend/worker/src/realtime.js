// Copyright (c) 2026, afmcoltd
import { createRealtimeHub } from "@shared/portalRealtime.js";
import { realtimeRoom } from "./session.js";

export const WORKER_EVENTS = [
  "driver_trip_update",
  "boarding_update",
  "boarding_confirmed",
  "boarding_unmarked",
  "boarding_arrived",
  "wait_request",
];

export const useWorkerRealtime = createRealtimeHub({
  socketGlobal: "masar_socket",
  events: WORKER_EVENTS,
  room: realtimeRoom,
});
