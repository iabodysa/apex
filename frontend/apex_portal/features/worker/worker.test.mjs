import { describe, expect, it, vi } from "vitest";

import { createWorkerGateway } from "./gateway.js";
import { workerRoutes } from "./routes.js";
import { createDraftAction } from "./asyncState.js";

describe("Masar worker feature", () => {
  it("publishes only the canonical worker routes", () => {
    expect(workerRoutes.map((route) => route.path)).toEqual([
      "/home",
      "/profile",
      "/accommodation",
      "/custody",
      "/transport",
      "/request-transport",
      "/requests",
      "/requests/:name",
    ]);
    expect(workerRoutes.every((route) => route.feature === "worker")).toBe(true);
    expect(workerRoutes.every((route) => route.capability.startsWith("worker."))).toBe(true);
  });

  it("uses token-scoped endpoints without accepting a worker id", async () => {
    const call = vi.fn().mockResolvedValue({ message: { employee_name: "عامل تجريبي" } });
    const gateway = createWorkerGateway(call);

    await expect(gateway.home()).resolves.toEqual({ employee_name: "عامل تجريبي" });
    expect(call).toHaveBeenCalledWith("apex.salis.api.masar.get_worker_home");
    expect(JSON.stringify(call.mock.calls)).not.toContain("employee");
  });

  it("keeps entered values after a recoverable submission error", async () => {
    const action = createDraftAction({ subject: "", description: "" });
    action.draft.subject = "طلب صيانة";
    action.draft.description = "المكيف لا يعمل";

    await action.submit(vi.fn().mockRejectedValue(new Error("network")));

    expect(action.state.value).toBe("error");
    expect(action.draft).toEqual({ subject: "طلب صيانة", description: "المكيف لا يعمل" });
  });
});
