import { describe, expect, it, vi } from "vitest";

import { createFleetSelfRoutes } from "./routes.js";
import { createSingleFlight } from "./state.js";

describe("Salis representative feature", () => {
  it("publishes the complete self-service route contract", () => {
    expect(createFleetSelfRoutes().map(({ path }) => path)).toEqual(["/", "/vehicle", "/vehicle/receipt", "/vehicle/return", "/fuel", "/fuel/request", "/fuel/additional", "/incidents", "/incidents/new", "/complaints", "/complaints/new", "/complaints/:name"]);
    expect(createFleetSelfRoutes().every((route) => route.feature === "fleet-self-service")).toBe(true);
    const capabilities = Object.fromEntries(createFleetSelfRoutes().map((route) => [route.path, route.capability]));
    expect(capabilities).toMatchObject({
      "/fuel": "fleet.self.fuel",
      "/incidents": "fleet.self.incident",
      "/complaints": "fleet.self.complaint",
      "/complaints/:name": "fleet.self.complaint",
      "/vehicle/receipt": "fleet.self.handover",
    });
  });

  it("coalesces repeat submits until the first request settles", async () => {
    let finish;
    const action = vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const submit = createSingleFlight();
    const first = submit("fuel", action);
    const second = submit("fuel", action);
    expect(second).toBe(first);
    expect(action).toHaveBeenCalledOnce();
    finish({ name: "FR-1", status: "Pending" });
    await expect(first).resolves.toMatchObject({ status: "Pending" });
  });
});
