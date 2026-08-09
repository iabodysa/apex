// Copyright (c) 2026, afmcoltd
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import * as helpers from "../fleetHelpers.js";
import { useFleetBoard } from "../useFleetBoard.js";
import { useAlerts } from "../useAlerts.js";
import { MAX_BULK_SELECTION, useSelection } from "../useSelection.js";

describe("Fleet OS presentation contracts", () => {
  it("renders enrichment reader error messages instead of object strings", () => {
    const normalize = helpers.normalizeReaderErrors || (() => []);

    expect(
      normalize([
        { reader: "drivers", error: "Could not load drivers." },
        "Could not load incidents.",
        { reader: "damages" },
      ]),
    ).toEqual(["Could not load drivers.", "Could not load incidents.", "damages"]);
  });

  it("keeps operation forms limited to fields their endpoints accept", () => {
    const stop = helpers.createStopForm ? helpers.createStopForm() : {};
    const theft = helpers.createTheftForm ? helpers.createTheftForm() : {};

    expect(Object.keys(stop).sort()).toEqual(["nextStatus", "notes", "reason"]);
    expect(Object.keys(theft).sort()).toEqual(["location", "police"]);
  });

  it("requires workshop release before assignment", () => {
    const canAssign = helpers.canAssignVehicle || (() => false);

    expect(canAssign({ vehicle_status: "available" })).toBe(true);
    expect(canAssign({ vehicle_status: "stopped" })).toBe(false);
    expect(canAssign({ vehicle_status: "workshop" })).toBe(false);
  });

  it("uses one status-tone contract across fleet views", () => {
    expect(helpers.vehicleStatusTone("assigned")).toBe("success");
    expect(helpers.vehicleStatusTone("stolen")).toBe("danger");
    expect(helpers.vehicleStatusTone("unknown")).toBe("neutral");
  });

  it("sends only released vehicles to the workshop", () => {
    expect(helpers.canSendToWorkshop({ vehicle_status: "available", current_driver: null })).toBe(true);
    expect(helpers.canSendToWorkshop({ vehicle_status: "stopped", current_driver: null })).toBe(true);
    expect(helpers.canSendToWorkshop({ vehicle_status: "available", current_driver: { name: "D-1" } })).toBe(false);
    expect(helpers.canSendToWorkshop({ vehicle_status: "stolen", current_driver: null })).toBe(false);
  });

  it("stops only active fleet states", () => {
    expect(helpers.canStopVehicle({ vehicle_status: "assigned" })).toBe(true);
    expect(helpers.canStopVehicle({ vehicle_status: "available" })).toBe(true);
    expect(helpers.canStopVehicle({ vehicle_status: "stopped" })).toBe(false);
    expect(helpers.canStopVehicle({ vehicle_status: "workshop" })).toBe(false);
    expect(helpers.canStopVehicle({ vehicle_status: "stolen" })).toBe(false);
  });

  it("allows only transitions backed by an explicit fleet command", () => {
    const canChoose = helpers.canChooseVehicleStatus;

    expect(canChoose({ vehicle_status: "available", current_driver: null }, "workshop")).toBe(true);
    expect(canChoose({ vehicle_status: "stopped", current_driver: null }, "available")).toBe(true);
    expect(canChoose({ vehicle_status: "assigned", current_driver: { name: "D-1" } }, "workshop")).toBe(false);
    expect(canChoose({ vehicle_status: "workshop", current_driver: null }, "stopped")).toBe(false);
    expect(canChoose({ vehicle_status: "stolen", current_driver: null }, "workshop")).toBe(false);
  });

  it("retains each bulk-operation outcome", () => {
    const normalize = helpers.normalizeBulkResult || (() => ({ rows: [] }));
    const result = normalize({
      succeeded: 1,
      failed: 1,
      results: [
        { plate: "A-1", ok: true },
        { plate: "B-2", ok: false, error: "Vehicle is already stopped" },
      ],
    });

    expect(result.succeeded).toBe(1);
    expect(result.failed).toBe(1);
    expect(result.rows).toEqual([
      { plate: "A-1", ok: true, error: "" },
      { plate: "B-2", ok: false, error: "Vehicle is already stopped" },
    ]);
  });

  it("counts workshop overstays in the attention inbox", () => {
    const board = useFleetBoard({ expiryFlag: () => ({ show: false }) });
    board.vehicles.value = [
      { vehicle_status: "workshop", workshop_overstay: true, history: [] },
      { vehicle_status: "workshop", workshop_overstay: false, history: [] },
    ];

    expect(board.triage.value.workshop).toBe(1);
  });

  it("does not invent a retired Desk route for an unbound alert", () => {
    const openWindow = vi.spyOn(window, "open").mockImplementation(() => null);
    const openVehicle = vi.fn();
    const alerts = useAlerts({
      vehicles: ref([]),
      t: (key) => key,
      openVehicle,
      closeAlerts: vi.fn(),
    });

    expect(alerts.openAlertTarget({ name: "TODO-1" })).toBe(false);
    expect(openVehicle).not.toHaveBeenCalled();
    expect(openWindow).not.toHaveBeenCalled();
    openWindow.mockRestore();
  });
});

describe("Fleet OS bulk-selection limit", () => {
  it("selects at most the server batch limit", () => {
    const filtered = ref(
      Array.from({ length: 55 }, (_, index) => ({ plate: `PLATE-${index + 1}` })),
    );
    const selection = useSelection(filtered);

    selection.toggleSelectAll();

    expect(MAX_BULK_SELECTION).toBe(50);
    expect(selection.selectedCount.value).toBe(50);
    expect(selection.selectionLimitReached.value).toBe(true);
  });

  it("does not add an individual vehicle after the limit", () => {
    const filtered = ref(
      Array.from({ length: 51 }, (_, index) => ({ plate: `PLATE-${index + 1}` })),
    );
    const selection = useSelection(filtered);
    for (let index = 0; index < 51; index += 1) {
      selection.toggleSelect(`PLATE-${index + 1}`);
    }

    expect(selection.selectedCount.value).toBe(50);
    expect(selection.isSelected("PLATE-51")).toBe(false);
  });

  it("keeps the limit visible after filters change", () => {
    const filtered = ref(
      Array.from({ length: 50 }, (_, index) => ({ plate: `PLATE-${index + 1}` })),
    );
    const selection = useSelection(filtered);

    selection.toggleSelectAll();
    filtered.value = [{ plate: "NEW-PLATE" }];

    expect(selection.selectionLimitReached.value).toBe(true);
  });
});
