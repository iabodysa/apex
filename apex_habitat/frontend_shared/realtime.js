// Copyright (c) 2026, AFMCO and contributors
// [#shared-realtime]
// createRealtime(config) builds the Frappe Socket.IO subscription shared by the
// board/live portals (fleet, safety, driver). Each of those hand-rolled the same
// socket wiring — read the injected `window.<portal>_socket` config, mirror
// socketio_client.js get_host() for dev vs prod, join a doctype room (the server
// gates the join on read permission), refetch on a push, and swallow EVERY
// failure path so the portal's own poll/fetch still carries the screen if the
// socket never connects. This factory holds that once; a portal supplies only
// what differs (its socket-config global, room doctype, event, and — for driver —
// the extra boarding-flow events on the same room).
import { io } from "socket.io-client";

// createRealtime({ socketGlobal, roomDoctype, event, extraEvents? }) -> connect
//   socketGlobal — window key holding the injected socket config, e.g.
//                  "fleet_socket" (site_name / socketio_port / enabled / dev_server)
//   roomDoctype  — doctype room to subscribe to, e.g. "Salis Vehicle"
//   event        — the push event that triggers a refetch, e.g. "fleet_update"
//   extraEvents  — optional extra events on the SAME room (driver boarding flow);
//                  delivered to the connect fn's second `onExtra(event, payload)` arg
// The returned connect(onUpdate, onExtra?) mirrors each portal's old
// connect<Portal>Realtime signature exactly.
export function createRealtime({ socketGlobal, roomDoctype, event, extraEvents = [] }) {
  // Socket config is injected by the portal's www/<portal>.py via a <script>.
  function cfg() {
    const c = (typeof window !== "undefined" && window[socketGlobal]) || {};
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
    const c = (typeof window !== "undefined" && window[socketGlobal]) || {};
    const dev = c.dev_server || window.dev_server;
    if (dev) {
      const parts = origin.split(":");
      const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
      return base + ":" + port + "/" + site;
    }
    return origin + "/" + site;
  }

  // Start the realtime subscription. `onUpdate` runs on each received `event`;
  // optional `onExtra(event, payload)` runs on each of `extraEvents`. Returns a
  // teardown function; safe to call even if the socket never started.
  return function connect(onUpdate, onExtra) {
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
      return () => {}; // socket.io unavailable — the portal's fetch/poll carries it
    }

    const joinRoom = () => {
      try {
        socket.emit("doctype_subscribe", roomDoctype);
      } catch (e) {
        /* a failed subscribe just means no realtime; the fetch/poll still runs */
      }
    };
    // Join on connect AND every reconnect (room membership is per-connection).
    socket.on("connect", joinRoom);
    socket.on("reconnect", joinRoom);
    socket.on(event, () => {
      try {
        onUpdate && onUpdate();
      } catch (e) {
        /* never let a handler error bubble into the socket layer */
      }
    });
    // Extra same-room events (only attached when a handler is supplied).
    if (extraEvents.length && onExtra) {
      for (const ev of extraEvents) {
        socket.on(ev, (payload) => {
          try {
            onExtra(ev, payload || {});
          } catch (e) {
            /* never let a handler error bubble into the socket layer */
          }
        });
      }
    }
    socket.on("connect_error", () => {
      /* swallow: the portal's own fetch/poll is the fallback path */
    });

    return () => {
      try {
        socket.emit("doctype_unsubscribe", roomDoctype);
        socket.off(event);
        for (const ev of extraEvents) socket.off(ev);
        socket.disconnect();
      } catch (e) {
        /* already gone */
      }
    };
  };
}
