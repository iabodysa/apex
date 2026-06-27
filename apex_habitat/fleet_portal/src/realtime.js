// Live board updates over Frappe's Socket.IO server: join the "Salis Vehicle"
// doctype room (server gates the join on read permission) and refetch on each
// `fleet_update`. The logged-in Desk session's `sid` cookie authenticates the
// socket. An enhancement over the 30s poll — every failure path is swallowed so
// the poll still carries the board if the socket never connects.
import { io } from "socket.io-client";

const EVENT = "fleet_update";
const ROOM_DOCTYPE = "Salis Vehicle";

// Socket config is injected by www/fleet.py via a <script> in fleet.html.
function cfg() {
  const c = (typeof window !== "undefined" && window.fleet_socket) || {};
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
  const c = (typeof window !== "undefined" && window.fleet_socket) || {};
  const dev = c.dev_server || window.dev_server;
  if (dev) {
    const parts = origin.split(":");
    const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
    return base + ":" + port + "/" + site;
  }
  return origin + "/" + site;
}

// Start the realtime subscription. `onUpdate` runs on each received fleet_update.
// Returns a teardown function; safe to call even if the socket never started.
export function connectFleetRealtime(onUpdate) {
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
    return () => {}; // socket.io unavailable — poll carries the board
  }

  const joinRoom = () => {
    try {
      socket.emit("doctype_subscribe", ROOM_DOCTYPE);
    } catch (e) {
      /* a failed subscribe just means no realtime; poll still runs */
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
    /* swallow: the poll is the fallback path */
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
