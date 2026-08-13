import { describe, expect, it, vi } from "vitest";

import { createFleetOperationsRoutes } from "./routes.js";
import { actionAvailability, createSingleFlight } from "./state.js";

describe("Salis fleet operations feature", () => {
  it("publishes the complete iPad route contract", () => {
    expect(createFleetOperationsRoutes().map(({ path }) => path)).toEqual(["/", "/vehicles", "/vehicles/:vehicle", "/assignments", "/handovers", "/handovers/:name", "/returns", "/returns/:name", "/fuel-approvals", "/incidents", "/incidents/:name", "/problems", "/problems/:name"]);
    expect(createFleetOperationsRoutes().every((route) => route.feature === "fleet-operations")).toBe(true);
  });

  it("derives unavailable buttons from server reasons and prevents double submit", async () => {
    expect(actionAvailability({ allowed: false, reason: "خارج نطاق مشروعك" })).toEqual({
      disabled: true,
      reason: "خارج نطاق مشروعك",
    });
    let finish;
    const action = vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const submit = createSingleFlight();
    const first = submit("approve:FR-1", action);
    const second = submit("approve:FR-1", action);
    expect(first).toBe(second);
    expect(action).toHaveBeenCalledOnce();
    finish({ status: "Approved" });
    await first;
  });
});
