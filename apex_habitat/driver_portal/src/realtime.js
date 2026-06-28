// Copyright (c) 2026, AFMCO and contributors
// Live trip updates over Frappe's Socket.IO server: join the "Dispatch Trip"
// doctype room (the server gates the join on read permission, so a driver only
// receives pushes for trips they can read) and refetch on each
// `driver_trip_update`. The logged-in session's `sid` cookie authenticates the
// socket. An enhancement over the manual fetch / pull-to-refresh — every failure
// path is swallowed so the existing fetch still carries the trips if the socket
// never connects. Mirrors fleet_portal/src/realtime.js.
import { io } from "socket.io-client";

const EVENT = "driver_trip_update";
const ROOM_DOCTYPE = "Dispatch Trip";

// Boarding-flow events on the same Dispatch Trip room (salis.api.boarding_flow):
// the manifest panel listens for these so a worker's claim / wait / boarding
// change repaints without a manual refresh. Each payload carries dispatch_trip.
const BOARDING_EVENTS = [
  "boarding_update",
  "wait_request",
  "boarding_claim",
  "boarding_rejected",
];

// Socket config is injected by www/driver.py via a <script> in driver.html.
function cfg() {
  const c = (typeof window !== "undefined" && window.driver_socket) || {};
  return {
    site: c.site_name || "",
    port: c.socketio_port || 9000,
    enabled: c.enabled !== false, // server sets enabled:false when async is off
  };
}

// Mirror socketio_client.js get_host(): same origin, site namespace; on a Vite
// dev server (different port from the socket port) target the socket port.
function host(site, port) {
  const origin = window.location.origin;
  // window.dev_server is a Desk-only global and is NOT set on a www portal page,
  // so read the injected flag first (server sets it from developer_mode). In dev
  // (no nginx) we must target host:socketio_port; in prod nginx proxies the origin.
  const c = (typeof window !== "undefined" && window.driver_socket) || {};
  const dev = c.dev_server || window.dev_server;
  if (dev) {
    const parts = origin.split(":");
    const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
    return base + ":" + port + "/" + site;
  }
  return origin + "/" + site;
}

// Start the realtime subscription. `onUpdate` runs on each received
// driver_trip_update. Optional `onBoarding(event, payload)` runs on each
// boarding-flow event (boarding_update / wait_request / boarding_claim /
// boarding_rejected) on the same room. Returns a teardown function; safe to call
// even if the socket never started.
export function connectDriverRealtime(onUpdate, onBoarding) {
  const { site, port, enabled } = cfg();
  if (!enabled || !site) return () => {};

  let socket;
  try {
    socket = io(host(site, port), {
      withCredentials: true,
      reconnectionAttempts: 5,
      // Same path Frappe's nginx/proxy exposes; cookie auth rides the request.
      secure: window.location.protocol === "https:",
    });
  } catch (e) {
    return () => {}; // socket.io unavailable — the manual fetch carries the trips
  }

  const joinRoom = () => {
    try {
      socket.emit("doctype_subscribe", ROOM_DOCTYPE);
    } catch (e) {
      /* a failed subscribe just means no realtime; the fetch still runs */
    }
  };
  // Join on connect AND every reconnect (room membership is per-connection).
  socket.on("connect", joinRoom);
  socket.on("reconnect", joinRoom);
  socket.on(EVENT, () => {
    try {
      onUpdate && onUpdate();
    } catch (e) {
      /* never let a handler error bubble into the socket layer */
    }
  });
  // Boarding-flow listeners (only attached when a handler is supplied).
  if (onBoarding) {
    for (const ev of BOARDING_EVENTS) {
      socket.on(ev, (payload) => {
        try {
          onBoarding(ev, payload || {});
        } catch (e) {
          /* never let a handler error bubble into the socket layer */
        }
      });
    }
  }
  socket.on("connect_error", () => {
    /* swallow: the manual fetch is the fallback path */
  });

  return () => {
    try {
      socket.emit("doctype_unsubscribe", ROOM_DOCTYPE);
      socket.off(EVENT);
      for (const ev of BOARDING_EVENTS) socket.off(ev);
      socket.disconnect();
    } catch (e) {
      /* already gone */
    }
  };
}
