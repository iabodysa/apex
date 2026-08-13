const LEAFLET_STYLE = "/assets/apex/vendor/leaflet-1.9.4/leaflet.css";
const LEAFLET_SCRIPT = "/assets/apex/vendor/leaflet-1.9.4/leaflet.js";
const DEFAULT_CENTER = Object.freeze([24.7136, 46.6753]);

function coordinatePair(point) {
  const pair = Array.isArray(point)
    ? [Number(point[0]), Number(point[1])]
    : [Number(point?.lat), Number(point?.lng)];
  return pair.every(Number.isFinite) ? pair : null;
}

export function routeCoordinates(item) {
  return (item?.path || []).map(coordinatePair).filter(Boolean);
}

function ensureLeafletStyle(documentSource) {
  if (documentSource.querySelector("link[data-apex-leaflet]")) return;
  const link = documentSource.createElement("link");
  link.rel = "stylesheet";
  link.href = LEAFLET_STYLE;
  link.dataset.apexLeaflet = "";
  documentSource.head.append(link);
}

function loadLeaflet({ documentSource, windowSource }) {
  ensureLeafletStyle(documentSource);
  if (windowSource.L) return Promise.resolve(windowSource.L);
  const existing = documentSource.querySelector("script[data-apex-leaflet]");
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(windowSource.L), { once: true });
      existing.addEventListener("error", reject, { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = documentSource.createElement("script");
    script.src = LEAFLET_SCRIPT;
    script.dataset.apexLeaflet = "";
    script.onload = () => resolve(windowSource.L);
    script.onerror = () => reject(new Error("تعذّر تحميل الخريطة."));
    documentSource.head.append(script);
  });
}

function driverPopup(documentSource, item) {
  const popup = documentSource.createElement("div");
  const driverName = documentSource.createElement("strong");
  driverName.textContent = item.driver_name || "السائق";
  const plate = documentSource.createElement("span");
  plate.textContent = item.plate || "";
  popup.append(driverName, documentSource.createElement("br"), plate);
  return popup;
}

export function createLeafletAdapter({
  documentSource = globalThis.document,
  windowSource = globalThis.window,
} = {}) {
  let map;
  let layer;
  let mountedRoot;

  async function draw(root, positions) {
    if (!root) return;
    if (map && mountedRoot !== root) destroy();
    const L = await loadLeaflet({ documentSource, windowSource });
    if (!map) {
      map = L.map(root, { zoomControl: true }).setView(DEFAULT_CENTER, 6);
      mountedRoot = root;
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
        crossOrigin: true,
      }).addTo(map);
      layer = L.layerGroup().addTo(map);
    }

    layer.clearLayers();
    const bounds = [];
    for (const item of positions) {
      const route = routeCoordinates(item);
      if (route.length > 1) {
        L.polyline(route, { color: "#079455", weight: 4, opacity: 0.8 }).addTo(layer);
      }
      for (const stop of item.stops || []) {
        const point = coordinatePair(stop);
        if (!point) continue;
        L.circleMarker(point, {
          radius: 5,
          color: "#07583a",
          fillColor: "#f5efe2",
          fillOpacity: 1,
        }).bindTooltip(stop.stop_name || "نقطة توقف").addTo(layer);
        bounds.push(point);
      }
      const driver = coordinatePair(item);
      if (item.has_position && driver) {
        L.circleMarker(driver, {
          radius: 9,
          color: "#ffffff",
          weight: 3,
          fillColor: item.stale ? "#b54708" : "#079455",
          fillOpacity: 1,
        }).bindPopup(driverPopup(documentSource, item)).addTo(layer);
        bounds.push(driver);
      }
      bounds.push(...route);
    }

    if (bounds.length) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 16 });
    else map.setView(DEFAULT_CENTER, 6);
    map.invalidateSize();
  }

  function destroy() {
    map?.remove();
    map = null;
    layer = null;
    mountedRoot = null;
  }

  return Object.freeze({ draw, destroy });
}
