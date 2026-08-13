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
});
