import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

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

  it("uses the native checklist-backed receipt and return service contract", () => {
    const component = readFileSync(
      join(process.cwd(), "features/fleet-self-service/components/VehicleHandoverForm.vue"),
      "utf8",
    );
    const receipt = readFileSync(
      join(process.cwd(), "features/fleet-self-service/pages/VehicleReceiptPage.vue"),
      "utf8",
    );
    const returned = readFileSync(
      join(process.cwd(), "features/fleet-self-service/pages/VehicleReturnPage.vue"),
      "utf8",
    );

    expect(component).toContain("apex.salis.api.fleet_employee_services.get_handover_checklist");
    expect(component).toContain("apex.salis.api.fleet_employee_services.receive_vehicle");
    expect(component).toContain("apex.salis.api.fleet_employee_services.return_vehicle");
    expect(component).toContain("checklist_template");
    expect(component).toContain("inspection_rows");
    expect(component).toContain("FileUploader");
    expect(receipt).toContain('direction="Receipt"');
    expect(returned).toContain('direction="Return"');
    expect(receipt).not.toContain("apex.salis.api.fleet_employee.receive_vehicle");
    expect(returned).not.toContain("apex.salis.api.fleet_employee.return_vehicle");

    const operationsReview = readFileSync(
      join(process.cwd(), "features/fleet-operations/pages/HandoverDetailPage.vue"),
      "utf8",
    );
    expect(operationsReview).toContain('doctype: "Vehicle Handover"');
    expect(operationsReview).not.toMatch(/receive_vehicle|return_vehicle|createResource/);
  });
});
