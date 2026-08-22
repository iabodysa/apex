import { io } from "socket.io-client";

function socketUrl(settings, origin) {
  const source = new URL(origin);
  const local = source.hostname === "localhost"
    || source.hostname === "127.0.0.1"
    || source.hostname.endsWith(".localhost");
  const base = local
    ? `${source.protocol}//${source.hostname}:${settings.socketio_port}`
    : origin;
  return `${base}/${settings.site_name}`;
}

export function createPortalSubscriber({
  settings = {},
  origin = globalThis.location?.origin || "",
  ioFactory = io,
} = {}) {
  if (!settings.site_name || !settings.socketio_port || !origin) return () => () => {};
  let socket;
  let room;
  let listeners = 0;
  let join;

  return (nextRoom, event, callback) => {
    if (!nextRoom || !event || typeof callback !== "function") return () => {};
    if (room && room !== nextRoom) throw new TypeError("Portal realtime owns one subject room");
    if (!socket) {
      room = nextRoom;
      socket = ioFactory(socketUrl(settings, origin), {
        withCredentials: true,
        reconnectionAttempts: 5,
        secure: globalThis.location?.protocol === "https:",
      });
      join = () => socket?.emit("task_subscribe", room);
      socket.on("connect", join);
      socket.on("reconnect", join);
    }
    socket.on(event, callback);
    listeners += 1;
    let active = true;
    return () => {
      if (!active || !socket) return;
      active = false;
      socket.off(event, callback);
      listeners -= 1;
      if (listeners) return;
      socket.emit("task_unsubscribe", room);
      socket.off("connect", join);
      socket.off("reconnect", join);
      socket.disconnect();
      socket = undefined;
      room = undefined;
      join = undefined;
    };
  };
}

// Separate from createPortalSubscriber on purpose: that one emits task_subscribe, which the
// server accepts with no permission check (correct for the Driver/Worker guest bearer-token
// audience — see frappe_handlers.js task_subscribe). This one emits doc_subscribe, which the
// server gates through frappe.has_permission(doctype, doc=docname, throw=True) before the
// caller ever joins the room (frappe/realtime.py can_subscribe_doc). Merging the two behind a
// flag would hide that the two calls carry different security guarantees from the call site.
export function createDocSubscriber({
  settings = {},
  origin = globalThis.location?.origin || "",
  ioFactory = io,
  doctype,
} = {}) {
  if (!settings.site_name || !settings.socketio_port || !origin || !doctype) return () => () => {};
  let socket;
  let docname;
  let listeners = 0;
  let join;

  return (nextDocname, event, callback) => {
    if (!nextDocname || !event || typeof callback !== "function") return () => {};
    if (docname && docname !== nextDocname) throw new TypeError("Portal doc realtime owns one document room");
    if (!socket) {
      docname = nextDocname;
      socket = ioFactory(socketUrl(settings, origin), {
        withCredentials: true,
        reconnectionAttempts: 5,
        secure: globalThis.location?.protocol === "https:",
      });
      join = () => socket?.emit("doc_subscribe", doctype, docname);
      socket.on("connect", join);
      socket.on("reconnect", join);
    }
    socket.on(event, callback);
    listeners += 1;
    let active = true;
    return () => {
      if (!active || !socket) return;
      active = false;
      socket.off(event, callback);
      listeners -= 1;
      if (listeners) return;
      socket.emit("doc_unsubscribe", doctype, docname);
      socket.off("connect", join);
      socket.off("reconnect", join);
      socket.disconnect();
      socket = undefined;
      docname = undefined;
      join = undefined;
    };
  };
}

export function connectContextRooms({ socket, entry, rooms }) {
  if (!socket || typeof socket.emit !== "function") {
    throw new TypeError("A Frappe realtime socket is required");
  }
  const joined = [...new Set(
    (Array.isArray(rooms) ? rooms : [])
      .filter((item) => item?.entry === entry && typeof item.room === "string" && item.room)
      .map((item) => item.room),
  )];
  const subscribe = () => {
    for (const room of joined) socket.emit("task_subscribe", room);
  };
  subscribe();
  socket.on?.("connect", subscribe);

  let connected = true;
  return () => {
    if (!connected) return;
    connected = false;
    socket.off?.("connect", subscribe);
    for (const room of joined) socket.emit("task_unsubscribe", room);
  };
}
