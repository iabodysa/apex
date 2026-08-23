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

// The third admission rule, and the one an operations BOARD needs: doctype_subscribe joins
// the room every row of one doctype is published to, gated on read permission for the doctype
// (realtime/handlers/frappe_handlers.js doctype_subscribe -> can_subscribe_doctype). A board
// watches a fleet, not one vehicle, so a doc room cannot express it and a token portal — which
// holds no DocPerm — is refused the join outright. The server side must name that room
// explicitly: publish_realtime given a doctype and no docname falls through to the site room
// (apex_core/utils/portal_live.py says where), so this subscriber only ever hears the events
// portal_live.notify_doctype sends.
// Unlike the two subscribers below this one holds SEVERAL rooms on one socket, because a
// doctype room carries no subject: an operations screen watching vehicles and trips at once
// is one operator's own permission set, not two audiences, and the server re-checks read
// permission on every join. A doc or task room is refused a second room for the opposite
// reason — the room id IS the subject there, so widening it would widen who is heard.
export function createDoctypeSubscriber({
  settings = {},
  origin = globalThis.location?.origin || "",
  ioFactory = io,
} = {}) {
  if (!settings.site_name || !settings.socketio_port || !origin) return () => () => {};
  let socket;
  let join;
  const rooms = new Map();

  return (doctype, event, callback) => {
    if (!doctype || !event || typeof callback !== "function") return () => {};
    if (!socket) {
      socket = ioFactory(socketUrl(settings, origin), {
        withCredentials: true,
        reconnectionAttempts: 5,
        secure: globalThis.location?.protocol === "https:",
      });
      join = () => rooms.forEach((_count, name) => socket?.emit("doctype_subscribe", name));
      socket.on("connect", join);
      socket.on("reconnect", join);
    }
    if (!rooms.has(doctype)) socket.emit("doctype_subscribe", doctype);
    rooms.set(doctype, (rooms.get(doctype) || 0) + 1);
    socket.on(event, callback);
    let active = true;
    return () => {
      if (!active || !socket) return;
      active = false;
      socket.off(event, callback);
      const left = (rooms.get(doctype) || 1) - 1;
      if (left) rooms.set(doctype, left);
      else {
        rooms.delete(doctype);
        socket.emit("doctype_unsubscribe", doctype);
      }
      if (rooms.size) return;
      socket.off("connect", join);
      socket.off("reconnect", join);
      socket.disconnect();
      socket = undefined;
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

