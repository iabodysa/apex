// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

export const connectFleetRealtime = createRealtime({
  socketGlobal: "fleet_socket",
  roomDoctype: "Salis Vehicle",
  event: "fleet_update",
});
