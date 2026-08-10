// Copyright (c) 2026, afmcoltd
import { io } from "socket.io-client";
import { onUnmounted, watch } from "vue";


function socketSettings(globalName) {
  const conf = (typeof window !== "undefined" && window[globalName]) || {};
  return {
    site: conf.site_name || "",
    port: conf.socketio_port || 9000,
    enabled: conf.enabled !== false,
    dev: !!conf.dev_server,
  };
}

function socketUrl({ site, port, dev }) {
  const origin = window.location.origin;
  if (!dev) return origin + "/" + site;
  const parts = origin.split(":");
  const base = parts.length > 2 ? parts[0] + ":" + parts[1] : origin;
  return base + ":" + port + "/" + site;
}

export function connectPortalRoom({ socketGlobal, room, events, onEvent }) {
  const settings = socketSettings(socketGlobal);
  if (!room || !settings.enabled || !settings.site) return () => {};

  let socket;
  try {
    socket = io(socketUrl(settings), {
      withCredentials: true,
      reconnectionAttempts: 5,
      secure: window.location.protocol === "https:",
    });
  } catch (e) {
    return () => {};
  }

  const join = () => {
    try {
      socket.emit("task_subscribe", room);
    } catch (e) {
    }
  };
  socket.on("connect", join);
  socket.on("reconnect", join);
  socket.on("connect_error", () => {
  });

  for (const name of events) {
    socket.on(name, (payload) => {
      try {
        onEvent(name, payload || {});
      } catch (e) {
      }
    });
  }

  return () => {
    try {
      socket.emit("task_unsubscribe", room);
      for (const name of events) socket.off(name);
      socket.disconnect();
    } catch (e) {
    }
  };
}

export function createRealtimeHub({ socketGlobal, events, room }) {
  const subscribers = new Set();
  let joinedRoom = "";
  let teardown = () => {};

  function fanout(event, payload) {
    for (const subscriber of [...subscribers]) {
      try {
        subscriber(event, payload);
      } catch (e) {
      }
    }
  }

  function bind(next) {
    if (next === joinedRoom) return;
    teardown();
    joinedRoom = next || "";
    teardown = joinedRoom
      ? connectPortalRoom({ socketGlobal, room: joinedRoom, events, onEvent: fanout })
      : () => {};
  }

  function release() {
    teardown();
    teardown = () => {};
    joinedRoom = "";
  }

  return function useRealtime(onEvent) {
    subscribers.add(onEvent);
    const stop = watch(room, (next) => bind(subscribers.size ? next : ""), {
      immediate: true,
    });
    onUnmounted(() => {
      stop();
      subscribers.delete(onEvent);
      if (!subscribers.size) release();
    });
  };
}
