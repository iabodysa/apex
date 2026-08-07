// Copyright (c) 2026, afmcoltd
import { io } from "socket.io-client";

export function createRealtime({ socketGlobal, roomDoctype, event, extraEvents = [] }) {
  function cfg() {
    const c = (typeof window !== "undefined" && window[socketGlobal]) || {};
    return {
      site: c.site_name || "",
      port: c.socketio_port || 9000,
      enabled: c.enabled !== false,
    };
  }

  function host(site, port) {
    const origin = window.location.origin;
    const c = (typeof window !== "undefined" && window[socketGlobal]) || {};
    const dev = c.dev_server || window.dev_server;
    if (dev) {
      const parts = origin.split(":");
      const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
      return base + ":" + port + "/" + site;
    }
    return origin + "/" + site;
  }

  return function connect(onUpdate, onExtra) {
    const { site, port, enabled } = cfg();
    if (!enabled || !site) return () => {};

    let socket;
    try {
      socket = io(host(site, port), {
        withCredentials: true,
        reconnectionAttempts: 5,
        secure: window.location.protocol === "https:",
      });
    } catch (e) {
      return () => {};
    }

    const joinRoom = () => {
      try {
        socket.emit("doctype_subscribe", roomDoctype);
      } catch (e) {
      }
    };
    socket.on("connect", joinRoom);
    socket.on("reconnect", joinRoom);
    socket.on(event, () => {
      try {
        onUpdate && onUpdate();
      } catch (e) {
      }
    });
    if (extraEvents.length && onExtra) {
      for (const ev of extraEvents) {
        socket.on(ev, (payload) => {
          try {
            onExtra(ev, payload || {});
          } catch (e) {
          }
        });
      }
    }
    socket.on("connect_error", () => {
    });

    return () => {
      try {
        socket.emit("doctype_unsubscribe", roomDoctype);
        socket.off(event);
        for (const ev of extraEvents) socket.off(ev);
        socket.disconnect();
      } catch (e) {
      }
    };
  };
}
