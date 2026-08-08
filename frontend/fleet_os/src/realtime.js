// Copyright (c) 2026, afmcoltd
import { createRealtime } from "@shared/realtime.js";

/* The `Salis Vehicle` doctype room, published after commit by the eight write paths. The socket
   server only delivers to recipients who may read the document, so project scope is honoured
   without any filtering here — and the payload is advisory: the client always refetches the
   board rather than trusting the message body. */
export const connectFleetRealtime = createRealtime({
  socketGlobal: "fleet_socket",
  roomDoctype: "Salis Vehicle",
  event: "fleet_update",
});
