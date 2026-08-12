import { describe, expect, it, vi } from "vitest";

import { FLEET_SELF_METHODS, createFleetSelfResources } from "./api.js";
import { createFleetSelfRoutes } from "./routes.js";
import { createSingleFlight } from "./state.js";

describe("Salis representative feature", () => {
  it("publishes the complete self-service route contract", () => {
    expect(createFleetSelfRoutes().map(({ path }) => path)).toEqual([
      "/",
      "/vehicle",
      "/vehicle/receipt",
      "/vehicle/return",
      "/fuel",
      "/fuel/request",
      "/fuel/additional",
      "/incidents",
      "/incidents/new",
      "/complaints",
      "/complaints/new",
      "/complaints/:name",
    ]);
    expect(
      createFleetSelfRoutes().every(
        (route) => route.feature === "fleet-self-service",
      ),
    ).toBe(true);
  });

  it("binds every write to the session-derived Salis API", () => {
    expect(FLEET_SELF_METHODS).toMatchObject({
      context: "apex.salis.api.fleet_employee.get_context",
      receiveVehicle: "apex.salis.api.fleet_employee.receive_vehicle",
      returnVehicle: "apex.salis.api.fleet_employee.return_vehicle",
      requestFuel: "apex.salis.api.fleet_employee.submit_fuel_request",
      requestAdditionalFuel:
        "apex.salis.api.fleet_employee.submit_additional_fuel_request",
      reportIncident: "apex.salis.api.fleet_employee.report_incident",
      createComplaint: "apex.salis.api.fleet_employee.create_complaint",
      replyComplaint: "apex.salis.api.fleet_employee.reply_to_complaint",
    });
    const factory = vi.fn((options) => options);
    const resources = createFleetSelfResources(factory);
    expect(resources.context.method).toBe("GET");
    expect(resources.reportIncident.method).toBe("POST");
    expect(JSON.stringify(resources)).not.toMatch(
      /driver_id|employee_id|user_id/,
    );
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
