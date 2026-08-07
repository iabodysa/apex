// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

export const connectSafetyRealtime = createRealtime({
  socketGlobal: "safety_socket",
  roomDoctype: "Safety Round",
  event: "safety_update",
});
