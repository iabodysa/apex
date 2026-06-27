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
  if (window.dev_server) {
    const parts = origin.split(":");
    const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
    return base + ":" + port + "/" + site;
  }
  return origin + "/" + site;
}

// Start the realtime subscription. `onUpdate` runs on each received
// driver_trip_update. Returns a teardown function; safe to call even if the
// socket never started.
export function connectDriverRealtime(onUpdate) {
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
  socket.on("connect_error", () => {
    /* swallow: the manual fetch is the fallback path */
  });

  return () => {
    try {
      socket.emit("doctype_unsubscribe", ROOM_DOCTYPE);
      socket.off(EVENT);
      socket.disconnect();
    } catch (e) {
      /* already gone */
    }
  };
}
