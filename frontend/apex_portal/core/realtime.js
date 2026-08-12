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
