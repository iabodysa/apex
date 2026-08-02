<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <section class="fleet-map">
    <header class="fm-bar">
      <div class="fm-title">
        <h2>{{ t("fleetMap.title") }}</h2>
        <p>{{ t("fleetMap.subtitle", { live: liveCount, total: rows.length }) }}</p>
      </div>
      <div class="fm-filters">
        <label class="fm-field">
          <span>{{ t("fleetMap.driver") }}</span>
          <select v-model="driverFilter" class="fm-select">
            <option value="">{{ t("fleetMap.allDrivers") }}</option>
            <option v-for="name in driverNames" :key="name" :value="name">{{ name }}</option>
          </select>
        </label>
        <label class="fm-field">
          <span>{{ t("fleetMap.plan") }}</span>
          <select v-model="planFilter" class="fm-select">
            <option value="">{{ t("fleetMap.allPlans") }}</option>
            <option v-for="plan in planNames" :key="plan.name" :value="plan.name">
              {{ plan.label }}
            </option>
          </select>
        </label>
        <button type="button" class="soft-btn" @click="load()">
          <Icon name="refresh" :size="15" /> {{ t("common.refresh") }}
        </button>
      </div>
    </header>

    <div class="fm-body">
      <div ref="mapEl" class="fm-canvas" />

      <EmptyState v-if="state === 'error'" class="fm-overlay-state" :title="error || t('fleetMap.loadError')">
        <template #icon><Icon name="triangle-alert" :size="20" :stroke-width="1.6" /></template>
        <template #action>
          <button class="soft-btn" @click="load()">{{ t("common.retry") }}</button>
        </template>
      </EmptyState>

      <EmptyState v-else-if="state === 'ready' && !liveCount" class="fm-overlay-state" :title="t('fleetMap.noneLive')"
                  :hint="t('fleetMap.noneLiveHint')">
        <template #icon><Icon name="pin" :size="20" :stroke-width="1.6" /></template>
      </EmptyState>

      <ul v-if="visible.length" class="fm-legend">
        <li v-for="row in visible" :key="row.dispatch_trip" :class="{ off: !row.has_position, stale: row.stale }">
          <span class="fm-dot" />
          <b>{{ row.driver_name || t("common.none") }}</b>
          <span>{{ row.route_name }}</span>
          <span v-if="row.plate" class="fm-plate">{{ row.plate }}</span>
          <span v-if="!row.has_position" class="fm-note">{{ t("fleetMap.noFix") }}</span>
          <span v-else-if="row.stale" class="fm-note">{{ t("map.stale", { age: "" }) }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../Icon.vue";
import { useI18n } from "../i18n";
import { getActiveDriverPositions } from "../api.js";

const { t, resourceErrorMessage } = useI18n();
const L = typeof window !== "undefined" ? window.L : undefined;

const rows = ref([]);
const state = ref("idle");
const error = ref("");
const driverFilter = ref("");
const planFilter = ref("");
const mapEl = ref(null);
let map = null;
let markers = new Map();
let routeLines = new Map();
let timer = null;
const POLL_MS = 15000;

const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 10;
const TILE_URL =
  (typeof window !== "undefined" && window.apex_map_tiles && window.apex_map_tiles.url) ||
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  (typeof window !== "undefined" && window.apex_map_tiles && window.apex_map_tiles.attribution) ||
  "© OpenStreetMap";

const visible = computed(() =>
  rows.value.filter(
    (row) =>
      (!driverFilter.value || row.driver_name === driverFilter.value) &&
      (!planFilter.value || row.route_plan === planFilter.value),
  ),
);
const liveCount = computed(() => visible.value.filter((row) => row.has_position).length);
const driverNames = computed(() =>
  [...new Set(rows.value.map((row) => row.driver_name).filter(Boolean))].sort(),
);
const planNames = computed(() =>
  rows.value.map((row) => ({ name: row.route_plan, label: row.route_name })),
);

function ensureMap() {
  if (!L || map || !mapEl.value) return;
  map = L.map(mapEl.value, { zoomControl: true, attributionControl: true }).setView(
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
  );
  L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION }).addTo(map);
}

function driverIcon(row) {
  return L.divIcon({
    className: "driver-marker" + (row.stale ? " is-stale" : ""),
    html: '<span class="dm-pulse"></span><span class="dm-core">🚌</span>',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

function drawRoutes() {
  if (!map) return;
  const wanted = new Set();
  for (const row of visible.value) {
    const points = (row.stops || []).filter((stop) => stop.lat && stop.lng);
    if (points.length < 2) continue;
    wanted.add(row.route_plan);
    const latlngs = points.map((stop) => [stop.lat, stop.lng]);
    const existing = routeLines.get(row.route_plan);
    if (existing) {
      existing.line.setLatLngs(latlngs);
    } else {
      const line = L.polyline(latlngs, { weight: 3, opacity: 0.75, dashArray: "6 6" }).addTo(map);
      line.bindTooltip(row.route_name, { sticky: true });
      const pins = points.map((stop, index) =>
        L.circleMarker([stop.lat, stop.lng], { radius: 5, weight: 2, fillOpacity: 1 })
          .bindTooltip(`${index + 1}. ${stop.stop_name || ""}`, { direction: "top" })
          .addTo(map),
      );
      routeLines.set(row.route_plan, { line, pins });
    }
  }
  for (const [key, drawn] of routeLines) {
    if (!wanted.has(key)) {
      map.removeLayer(drawn.line);
      drawn.pins.forEach((pin) => map.removeLayer(pin));
      routeLines.delete(key);
    }
  }
}

function drawMarkers() {
  if (!map) return;
  const wanted = new Set();
  for (const row of visible.value) {
    if (!row.has_position) continue;
    wanted.add(row.dispatch_trip);
    const position = [row.lat, row.lng];
    const existing = markers.get(row.dispatch_trip);
    if (existing) {
      existing.setLatLng(position).setIcon(driverIcon(row));
    } else {
      const marker = L.marker(position, { icon: driverIcon(row) }).addTo(map);
      marker.bindTooltip(`${row.driver_name || ""} · ${row.route_name}`, { direction: "top" });
      markers.set(row.dispatch_trip, marker);
    }
  }
  for (const [key, marker] of markers) {
    if (!wanted.has(key)) {
      map.removeLayer(marker);
      markers.delete(key);
    }
  }
  drawRoutes();

  const drawn = [...markers.values(), ...[...routeLines.values()].map((r) => r.line)];
  if (drawn.length > 1) map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.2));
  else if (drawn.length === 1) map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.4));
}

async function load() {
  try {
    rows.value = await getActiveDriverPositions();
    state.value = "ready";
    error.value = "";
    await nextTick();
    ensureMap();
    drawMarkers();
  } catch (e) {
    state.value = "error";
    error.value = resourceErrorMessage(e, "fleetMap.loadError");
  }
}

watch(visible, drawMarkers);

onMounted(() => {
  load();
  timer = setInterval(() => {
    if (!document.hidden) load();
  }, POLL_MS);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
  if (map) {
    map.remove();
    map = null;
  }
  markers = new Map();
  routeLines = new Map();
});
</script>

<style scoped>
.fleet-map {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.fm-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.fm-title h2 {
  margin: 0;
  font-size: 17px;
}
.fm-title p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--c-muted);
}
.fm-filters {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.fm-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11.5px;
  color: var(--c-muted);
}
.fm-select {
  min-width: 150px;
  padding: 7px 10px;
  border-radius: 10px;
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  color: var(--c-ink);
  font-size: 13px;
}
.fm-body {
  position: relative;
  flex: 1;
  min-height: 420px;
}
.fm-canvas {
  position: absolute;
  inset: 0;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--c-border);
}
.fm-overlay-state {
  /* Centering is a physical fact, not a reading-direction one: inset-inline-start flips
     under RTL while the translate does not, which pushed the panel off the canvas. */
  position: absolute;
  left: 50%;
  top: 40%;
  transform: translate(-50%, -50%);
  max-width: min(320px, 80%);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
}
.fm-legend {
  position: absolute;
  inset-block-end: 12px;
  inset-inline-start: 12px;
  max-height: 40%;
  overflow: auto;
  margin: 0;
  padding: 8px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: color-mix(in srgb, var(--c-surface) 92%, transparent);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  font-size: 12px;
}
.fm-legend li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fm-legend .fm-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-primary);
  flex: none;
}
.fm-legend li.off .fm-dot {
  background: var(--c-muted);
}
.fm-legend li.stale .fm-dot {
  background: var(--c-warning, #b8860b);
}
.fm-plate {
  font-variant-numeric: tabular-nums;
  color: var(--c-muted);
}
.fm-note {
  color: var(--c-muted);
  font-size: 11px;
}
</style>
