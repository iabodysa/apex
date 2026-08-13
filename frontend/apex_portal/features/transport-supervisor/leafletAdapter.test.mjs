import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { describe, expect, it, vi } from "vitest";

const modulePath = path.join(path.dirname(fileURLToPath(import.meta.url)), "leafletAdapter.js");

async function loadModule() {
  expect(existsSync(modulePath)).toBe(true);
  return import(/* @vite-ignore */ pathToFileURL(modulePath).href);
}

function leafletFixture() {
  const map = {
    setView: vi.fn().mockReturnThis(),
    fitBounds: vi.fn(),
    invalidateSize: vi.fn(),
    remove: vi.fn(),
  };
  const layer = { addTo: vi.fn().mockReturnThis(), clearLayers: vi.fn() };
  const addTo = vi.fn().mockReturnThis();
  const bindTooltip = vi.fn(() => ({ addTo }));
  const bindPopup = vi.fn(() => ({ addTo }));
  const leaflet = {
    map: vi.fn(() => map),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    layerGroup: vi.fn(() => layer),
    polyline: vi.fn(() => ({ addTo })),
    circleMarker: vi.fn(() => ({ bindTooltip, bindPopup })),
  };
  return { leaflet, map, layer };
}

describe("Leaflet adapter", () => {
  it("normalizes route geometry and owns map drawing and disposal", async () => {
    const { createLeafletAdapter, routeCoordinates } = await loadModule();
    expect(routeCoordinates({ path: [[24.7, 46.6], { lat: "24.8", lng: "46.7" }, ["bad", 1]] }))
      .toEqual([[24.7, 46.6], [24.8, 46.7]]);

    const { leaflet, map, layer } = leafletFixture();
    const adapter = createLeafletAdapter({
      windowSource: { L: leaflet },
      documentSource: document,
    });
    const root = document.createElement("div");
    await adapter.draw(root, [{
      route_name: "Airport route",
      path: [[24.7, 46.6], [24.8, 46.7]],
      stops: [{ lat: 24.75, lng: 46.65, stop_name: "Stop A" }],
      has_position: true,
      lat: 24.76,
      lng: 46.66,
      driver_name: "Driver A",
      plate: "ABC 123",
    }]);

    expect(leaflet.map).toHaveBeenCalledWith(root, { zoomControl: true });
    expect(layer.clearLayers).toHaveBeenCalledOnce();
    expect(leaflet.polyline).toHaveBeenCalledOnce();
    expect(leaflet.circleMarker).toHaveBeenCalledTimes(2);
    expect(map.fitBounds).toHaveBeenCalledOnce();
    expect(map.invalidateSize).toHaveBeenCalledOnce();

    const replacementRoot = document.createElement("div");
    await adapter.draw(replacementRoot, []);
    expect(map.remove).toHaveBeenCalledOnce();
    expect(leaflet.map).toHaveBeenCalledTimes(2);

    adapter.destroy();
    expect(map.remove).toHaveBeenCalledTimes(2);
  });

  it("reads semantic map colors from Apex design tokens", async () => {
    const { createLeafletAdapter, mapTheme } = await loadModule();
    const tokens = {
      "--brand-green": "#00844e",
      "--ink": "#072b1a",
      "--surface": "#f8f5ee",
      "--surface-2": "#ffffff",
      "--warn": "#a76609",
    };
    const windowSource = {
      L: leafletFixture().leaflet,
      getComputedStyle: () => ({ getPropertyValue: (name) => tokens[name] || "" }),
    };
    expect(mapTheme(document, windowSource)).toEqual({
      primary: "#00844e",
      ink: "#072b1a",
      surface: "#f8f5ee",
      ring: "#ffffff",
      stale: "#a76609",
    });

    const { leaflet } = leafletFixture();
    windowSource.L = leaflet;
    const adapter = createLeafletAdapter({ documentSource: document, windowSource });
    await adapter.draw(document.createElement("div"), [{
      path: [[24.7, 46.6], [24.8, 46.7]],
      stops: [{ lat: 24.75, lng: 46.65 }],
      has_position: true,
      stale: true,
      lat: 24.76,
      lng: 46.66,
    }]);
    expect(leaflet.polyline).toHaveBeenCalledWith(expect.any(Array), expect.objectContaining({ color: "#00844e" }));
    expect(leaflet.circleMarker).toHaveBeenNthCalledWith(1, expect.any(Array), expect.objectContaining({ color: "#072b1a", fillColor: "#f8f5ee" }));
    expect(leaflet.circleMarker).toHaveBeenNthCalledWith(2, expect.any(Array), expect.objectContaining({ color: "#ffffff", fillColor: "#a76609" }));
  });
});
