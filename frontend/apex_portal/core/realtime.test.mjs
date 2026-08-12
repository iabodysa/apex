import { describe, expect, it, vi } from "vitest";
import { connectContextRooms } from "./realtime.js";

describe("portal realtime", () => {
  it("joins only valid server-returned rooms for the active context", () => {
    const socket = { emit: vi.fn() };
    const disconnect = connectContextRooms({
      socket,
      entry: "worker",
      rooms: [
        { entry: "worker", room: "worker:opaque-a" },
        { entry: "driver", room: "driver:opaque-b" },
        { entry: "worker", room: "worker:opaque-a" },
        { entry: "worker", room: "" },
      ],
    });

    expect(socket.emit).toHaveBeenCalledTimes(1);
    expect(socket.emit).toHaveBeenCalledWith("task_subscribe", "worker:opaque-a");

    disconnect();
    expect(socket.emit).toHaveBeenLastCalledWith("task_unsubscribe", "worker:opaque-a");
  });

  it("fails closed when no Frappe socket is supplied", () => {
    expect(() => connectContextRooms({ socket: null, entry: "worker", rooms: [] }))
      .toThrow(/socket/);
  });

  it("resubscribes after the native socket reconnects and removes its listener", () => {
    const listeners = new Map();
    const socket = {
      emit: vi.fn(),
      on: vi.fn((event, listener) => listeners.set(event, listener)),
      off: vi.fn((event, listener) => {
        if (listeners.get(event) === listener) listeners.delete(event);
      }),
    };
    const disconnect = connectContextRooms({
      socket,
      entry: "worker",
      rooms: [{ entry: "worker", room: "worker:opaque-a" }],
    });
    socket.emit.mockClear();

    listeners.get("connect")();
    expect(socket.emit).toHaveBeenCalledWith("task_subscribe", "worker:opaque-a");
    disconnect();
    expect(socket.off).toHaveBeenCalledWith("connect", expect.any(Function));
    expect(listeners.has("connect")).toBe(false);
  });
});
