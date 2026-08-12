import { describe, expect, it, vi } from "vitest";
import { reconcileServiceWorker } from "./serviceWorker.js";

describe("service-worker registration", () => {
  it("removes only known legacy or same-entry wrong-scope registrations", async () => {
    const origin = globalThis.location.origin;
    const legacy = { active: { scriptURL: `${origin}/driver-sw.js` }, scope: `${origin}/driver/`, unregister: vi.fn() };
    const wrongScope = { active: { scriptURL: `${origin}/driver-sw.min.js` }, scope: `${origin}/driver`, unregister: vi.fn() };
    const other = { active: { scriptURL: `${origin}/service-worker.js` }, scope: `${origin}/`, unregister: vi.fn() };
    const register = vi.fn();
    await reconcileServiceWorker({ getRegistrations: async () => [legacy, wrongScope, other], register }, {
      service_worker_url: "/driver-sw.min.js",
      service_worker_scope: "/driver/",
    });

    expect(legacy.unregister).toHaveBeenCalledOnce();
    expect(wrongScope.unregister).toHaveBeenCalledOnce();
    expect(other.unregister).not.toHaveBeenCalled();
    expect(register).toHaveBeenCalledWith("/driver-sw.min.js", { scope: "/driver/" });
  });
});
