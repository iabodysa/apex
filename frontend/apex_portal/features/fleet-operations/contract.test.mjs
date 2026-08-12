import { describe, expect, it, vi } from "vitest";

import {
  FLEET_OPERATIONS_METHODS,
  createFleetOperationsResources,
} from "./api.js";
import { createFleetOperationsRoutes } from "./routes.js";
import { actionAvailability, createSingleFlight } from "./state.js";

describe("Salis fleet operations feature", () => {
  it("publishes the complete iPad route contract", () => {
    expect(createFleetOperationsRoutes().map(({ path }) => path)).toEqual([
      "/",
      "/vehicles",
      "/vehicles/:vehicle",
      "/assignments",
      "/handovers",
      "/returns",
      "/fuel-approvals",
      "/incidents",
      "/incidents/:name",
      "/problems",
      "/problems/:name",
    ]);
    expect(
      createFleetOperationsRoutes().every(
        (route) => route.feature === "fleet-operations",
      ),
    ).toBe(true);
  });

  it("uses project-scoped server queues and native workflow actions", () => {
    expect(FLEET_OPERATIONS_METHODS).toMatchObject({
      overview: "apex.salis.api.fleet_os.get_operations_overview",
      vehicles: "apex.salis.api.fleet_os.get_fleet_os",
      fuelQueue: "apex.salis.api.fuel_console.get_pending_fuel_requests",
      approveFuel: "apex.salis.api.fuel_console.approve_fuel_request",
      rejectFuel: "apex.salis.api.fuel_console.reject_fuel_request",
    });
    const factory = vi.fn((options) => options);
    const resources = createFleetOperationsResources(factory);
    expect(resources.overview.method).toBe("GET");
    expect(resources.approveFuel.method).toBe("POST");
  });

  it("derives unavailable buttons from server reasons and prevents double submit", async () => {
    expect(
      actionAvailability({ allowed: false, reason: "خارج نطاق مشروعك" }),
    ).toEqual({
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
