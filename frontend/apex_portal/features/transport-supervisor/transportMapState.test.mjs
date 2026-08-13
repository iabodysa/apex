import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const modulePath = path.join(path.dirname(fileURLToPath(import.meta.url)), "transportMapState.js");

async function loadModule() {
  expect(existsSync(modulePath)).toBe(true);
  return import(/* @vite-ignore */ pathToFileURL(modulePath).href);
}

describe("transport map state", () => {
  it("owns loading, unique filter options, and visible positions", async () => {
    const { createTransportMapState } = await loadModule();
    const mapState = createTransportMapState();

    await mapState.load(async () => ({
      positions: [
        { dispatch_trip: "TRIP-1", project: "Project A", status: "Running" },
        { dispatch_trip: "TRIP-2", project: "Project B", status: "Waiting" },
        { dispatch_trip: "TRIP-3", project: "Project A", status: "Waiting" },
      ],
    }));

    expect(mapState.phase.value).toBe("ready");
    expect(mapState.projects.value).toEqual(["Project A", "Project B"]);
    expect(mapState.statuses.value).toEqual(["Running", "Waiting"]);
    mapState.project.value = "Project A";
    mapState.status.value = "Waiting";
    expect(mapState.visible.value.map((row) => row.dispatch_trip)).toEqual(["TRIP-3"]);
  });

  it("returns only the selected trip for viewport framing", async () => {
    const { selectedMapRows } = await loadModule();
    const rows = [
      { dispatch_trip: "RIYADH", lat: 24.7, lng: 46.7 },
      { dispatch_trip: "JEDDAH", lat: 21.5, lng: 39.2 },
    ];

    expect(selectedMapRows(rows, "JEDDAH")).toEqual([rows[1]]);
    expect(selectedMapRows(rows, "MISSING")).toEqual([]);
  });

  it("distinguishes empty, denied, and failed reads", async () => {
    const { createTransportMapState } = await loadModule();
    const mapState = createTransportMapState();

    await mapState.load(async () => ({ positions: [] }));
    expect(mapState.phase.value).toBe("empty");

    await mapState.load(async () => { throw { status: 403 }; });
    expect(mapState.phase.value).toBe("denied");

    await mapState.load(async () => { throw new Error("server failed"); });
    expect(mapState.phase.value).toBe("error");
    expect(mapState.error.value).toBe("server failed");
  });

  it("normalizes coordinate validity before a position can be presented as live", async () => {
    const { coordinatePair, createTransportMapState } = await loadModule();
    expect(coordinatePair({ lat: 24.7, lng: 46.7 })).toEqual([24.7, 46.7]);
    expect(coordinatePair({ lat: 46.7, lng: 24.7 })).toBeNull();
    expect(coordinatePair({ lat: 0, lng: 0 })).toBeNull();
    expect(coordinatePair({ lat: 90, lng: 181 })).toBeNull();

    const mapState = createTransportMapState();
    await mapState.load(async () => ({
      positions: [
        { dispatch_trip: "VALID", has_position: true, lat: "24.7", lng: "46.7" },
        { dispatch_trip: "SWAPPED", has_position: true, lat: 46.7, lng: 24.7 },
        { dispatch_trip: "ZERO", has_position: true, lat: 0, lng: 0 },
      ],
    }));

    expect(mapState.positions.value).toEqual([
      expect.objectContaining({ dispatch_trip: "VALID", has_position: true, position_available: true, lat: 24.7, lng: 46.7 }),
      expect.objectContaining({ dispatch_trip: "SWAPPED", has_position: false, position_available: false, lat: null, lng: null }),
      expect.objectContaining({ dispatch_trip: "ZERO", has_position: false, position_available: false, lat: null, lng: null }),
    ]);
  });
});
