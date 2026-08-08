<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="fleet-map">
    <header class="fm-bar">
      <div class="fm-title">
        <h2>{{ t("fleetMap.title") }}</h2>
        <p>{{ t("fleetMap.subtitle", { live: liveCount, total: rows.length }) }}</p>
      </div>
      <div class="fm-filters">
        <FormControl
          type="select"
          size="md"
          :label="t('fleetMap.driver')"
          :options="driverOptions"
          :model-value="driverFilter"
          @update:model-value="setFilter('driver', $event)"
        />
        <FormControl
          type="select"
          size="md"
          :label="t('fleetMap.plan')"
          :options="planOptions"
          :model-value="planFilter"
          @update:model-value="setFilter('plan', $event)"
        />
        <Button variant="outline" size="xl" :label="t('common.refresh')" @click="load()">
          <template #prefix><Icon name="refresh" :size="15" /></template>
        </Button>
      </div>
    </header>

    <div class="fm-body">
      <div v-if="hasLeaflet" ref="mapEl" class="fm-canvas" />

      <!-- The single-driver map has always drawn a coordinate readout when the library is
           missing; without the same fallback here the page was a permanently blank rectangle
           with nothing saying why. -->
      <div v-else class="fm-fallback">
        <Alert theme="yellow" :title="t('map.unavailable')" :dismissable="false" />
        <ul v-if="visible.length" class="fm-coords">
          <li v-for="row in visible" :key="row.dispatch_trip">
            <b>{{ row.driver_name || t("common.none") }}</b>
            <span>{{ row.route_name }}</span>
            <bdi v-if="row.has_position">{{ row.lat.toFixed(5) }}, {{ row.lng.toFixed(5) }}</bdi>
            <span v-else class="fm-note">{{ t("fleetMap.noFix") }}</span>
          </li>
        </ul>
      </div>

      <Alert
        v-if="hasLeaflet && tilesDown"
        class="fm-tile-note"
        theme="yellow"
        :title="t('map.tilesUnavailable')"
        :dismissable="false"
      />

      <LoadError
        v-if="state === 'error'"
        class="fm-overlay-state"
        :title="t('fleetMap.loadError')"
        :detail="error"
        :hint="t('list.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="load()"
      />

      <EmptyState
        v-else-if="state === 'ready' && !liveCount"
        class="fm-overlay-state"
        :title="t('fleetMap.noneLive')"
        :hint="t('fleetMap.noneLiveHint')"
      >
        <template #icon><Icon name="pin" :size="20" :stroke-width="1.6" /></template>
      </EmptyState>

      <ul v-if="hasLeaflet && visible.length" class="fm-legend">
        <li
          v-for="row in visible"
          :key="row.dispatch_trip"
          :class="{ off: !row.has_position, stale: row.stale }"
        >
          <span class="fm-dot" />
          <b>{{ row.driver_name || t("common.none") }}</b>
          <span>{{ row.route_name }}</span>
          <bdi v-if="row.plate" class="fm-plate">{{ row.plate }}</bdi>
          <span v-if="!row.has_position" class="fm-note">{{ t("fleetMap.noFix") }}</span>
          <span v-else-if="row.stale" class="fm-note">{{ t("fleetMap.staleShort") }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Alert, Button, FormControl } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import { usePoll } from "@shared/usePoll.js";

import Icon from "../Icon.vue";
import { getActiveDriverPositions } from "../api.js";
import { createSequence } from "../fmt.js";
import { TILE_ATTRIBUTION, TILE_URL, leaflet } from "../mapTiles.js";
import { useI18n } from "@/i18n";

const { t, resourceErrorMessage } = useI18n();
const route = useRoute();
const router = useRouter();
const L = leaflet();
const hasLeaflet = Boolean(L);

const rows = ref([]);
const state = ref("idle");
const error = ref("");
const tilesDown = ref(false);
const mapEl = ref(null);
const seq = createSequence();
let map = null;
let markers = new Map();
let routeLines = new Map();
const POLL_MS = 15000;

const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 10;

/* Both filters live in the address so a supervisor can send "these drivers, this plan" to a
   colleague and refresh without losing the narrowing he just did. */
const driverFilter = computed(() => String(route.query.driver || ""));
const planFilter = computed(() => String(route.query.plan || ""));

function setFilter(key, value) {
  const query = { ...route.query };
  if (value) query[key] = value;
  else delete query[key];
  router.replace({ name: "map", query });
}

const visible = computed(() =>
  rows.value.filter(
    (row) =>
      (!driverFilter.value || row.driver_name === driverFilter.value) &&
      (!planFilter.value || row.route_plan === planFilter.value),
  ),
);
const liveCount = computed(() => visible.value.filter((row) => row.has_position).length);

const driverOptions = computed(() => [
  { label: t("fleetMap.allDrivers"), value: "" },
  ...[...new Set(rows.value.map((row) => row.driver_name).filter(Boolean))]
    .sort()
    .map((name) => ({ label: name, value: name })),
]);

/* Two live trips can share one route plan, so the rows are collapsed by plan before they
   become options — mapping rows straight to options produced duplicate keys and a list that
   offered the same plan twice. */
const planOptions = computed(() => {
  const byPlan = new Map();
  for (const row of rows.value) {
    if (row.route_plan && !byPlan.has(row.route_plan)) {
      byPlan.set(row.route_plan, row.route_name || row.route_plan);
    }
  }
  return [
    { label: t("fleetMap.allPlans"), value: "" },
    ...[...byPlan.entries()].map(([value, label]) => ({ label, value })),
  ];
});

function ensureMap() {
  if (!hasLeaflet || map || !mapEl.value) return;
  map = L.map(mapEl.value, { zoomControl: true, attributionControl: true }).setView(
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
  );
  L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION })
    .on("tileerror", () => {
      tilesDown.value = true;
    })
    .on("tileload", () => {
      tilesDown.value = false;
    })
    .addTo(map);
}

function driverIcon(row) {
  return L.divIcon({
    className: "driver-marker" + (row.stale ? " is-stale" : ""),
    html: '<span class="dm-pulse" data-motion="loop"></span><span class="dm-core">\u{1F68C}</span>',
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
    const latlngs = row.path && row.path.length > 1 ? row.path : points.map((s) => [s.lat, s.lng]);
    const existing = routeLines.get(row.route_plan);
    if (existing) {
      existing.line.setLatLngs(latlngs);
      continue;
    }
    const onRoad = Boolean(row.path && row.path.length > 1);
    const line = L.polyline(latlngs, {
      weight: onRoad ? 5 : 3,
      opacity: onRoad ? 0.85 : 0.7,
      dashArray: onRoad ? null : "6 6",
    }).addTo(map);
    line.bindTooltip(row.route_name, { sticky: true });
    const pins = points.map((stop, index) =>
      L.circleMarker([stop.lat, stop.lng], { radius: 5, weight: 2, fillOpacity: 1 })
        .bindTooltip(`${index + 1}. ${stop.stop_name || ""}`, { direction: "top" })
        .addTo(map),
    );
    routeLines.set(row.route_plan, { line, pins });
  }
  for (const [key, drawn] of routeLines) {
    if (wanted.has(key)) continue;
    map.removeLayer(drawn.line);
    drawn.pins.forEach((pin) => map.removeLayer(pin));
    routeLines.delete(key);
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
      continue;
    }
    const marker = L.marker(position, { icon: driverIcon(row) }).addTo(map);
    marker.bindTooltip(`${row.driver_name || ""} · ${row.route_name}`, { direction: "top" });
    markers.set(row.dispatch_trip, marker);
  }
  for (const [key, marker] of markers) {
    if (wanted.has(key)) continue;
    map.removeLayer(marker);
    markers.delete(key);
  }
  drawRoutes();

  const drawn = [...markers.values(), ...[...routeLines.values()].map((r) => r.line)];
  if (drawn.length > 1) map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.2));
  else if (drawn.length === 1) map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.4));
}

async function load() {
  const ticket = seq.next();
  try {
    const res = await getActiveDriverPositions();
    if (!seq.isCurrent(ticket)) return;
    rows.value = res || [];
    state.value = "ready";
    error.value = "";
    await nextTick();
    ensureMap();
    drawMarkers();
  } catch (e) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(e, "fleetMap.loadError");
  }
}

watch(visible, drawMarkers);

usePoll(load, POLL_MS);
onMounted(load);

onUnmounted(() => {
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
  gap: var(--sp-3);
  height: 100%;
}
.fm-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-3);
}
.fm-title h2 {
  margin: 0;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
}
.fm-title p {
  margin: 2px 0 0;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.fm-filters {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-3);
  flex-wrap: wrap;
}
.fm-filters :deep(.space-y-1\.5) {
  min-width: 170px;
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
  border: var(--border-width) solid var(--c-border);
}
.fm-fallback {
  position: absolute;
  inset: 0;
  overflow-y: auto;
  padding: var(--sp-4);
  border-radius: var(--radius);
  border: var(--border-width) dashed var(--c-border-strong);
  background: var(--c-surface);
}
.fm-coords {
  list-style: none;
  margin: var(--sp-4) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}
.fm-coords li {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  align-items: baseline;
}
.fm-tile-note {
  position: absolute;
  inset-block-start: var(--sp-3);
  inset-inline: var(--sp-3);
  z-index: 450;
}
.fm-overlay-state {
  position: absolute;
  left: 50%;
  top: 40%;
  transform: translate(-50%, -50%);
  width: min(340px, 84%);
  padding: var(--sp-4);
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  z-index: 460;
}
.fm-legend {
  position: absolute;
  inset-block-end: var(--sp-3);
  inset-inline-start: var(--sp-3);
  max-height: 40%;
  overflow: auto;
  margin: 0;
  padding: var(--sp-2);
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: color-mix(in srgb, var(--c-surface) 92%, transparent);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  font-size: var(--fs-xs);
  z-index: 440;
}
.fm-legend li {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
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
  background: var(--c-warning);
}
.fm-plate {
  font-variant-numeric: tabular-nums;
  color: var(--c-muted);
}
.fm-note {
  color: var(--c-muted);
}
</style>
