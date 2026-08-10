<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="fleet-map">
    <MetricRibbon :metrics="signalMetrics" />

    <header class="fleet-map-tools">
      <div class="fleet-map-filters">
        <FormControl
          type="select"
          size="md"
          :label="t('fleetMap.driver')"
          :options="driverOptions"
          :model-value="driverSelectValue"
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
        <Button
          variant="outline"
          size="xl"
          :label="t('common.refresh')"
          :loading="state === 'loading'"
          @click="loadFirst()"
        >
          <template #prefix><Icon name="refresh" :size="15" /></template>
        </Button>
      </div>
    </header>

    <div class="fleet-map-layout">
      <div class="fleet-map-canvas-wrap">
        <div v-if="hasLeaflet" ref="mapEl" class="fleet-map-canvas" />

        <div v-else class="fleet-map-fallback">
          <Alert theme="yellow" :title="t('map.unavailable')" :dismissable="false" />
          <ul v-if="visible.length" class="fleet-map-coordinates">
            <li v-for="row in visible" :key="row.dispatch_trip">
              <b><bdi dir="auto">{{ row.driver_name || t("common.none") }}</bdi></b>
              <bdi dir="auto">{{ row.route_name }}</bdi>
              <bdi v-if="row.has_position">{{ row.lat.toFixed(5) }}, {{ row.lng.toFixed(5) }}</bdi>
              <span v-else>{{ t("fleetMap.noFix") }}</span>
            </li>
          </ul>
        </div>

        <Alert
          v-if="hasLeaflet && tilesDown"
          class="fleet-map-tile-note"
          theme="yellow"
          :title="t('map.tilesUnavailable')"
          :dismissable="false"
        />

        <LoadError
          v-if="state === 'error'"
          class="fleet-map-overlay"
          :title="t('fleetMap.loadError')"
          :detail="error"
          :hint="t('list.loadErrorHint')"
          :retry-label="t('common.retry')"
          @retry="loadFirst()"
        />

        <EmptyState
          v-else-if="state === 'ready' && !rows.length"
          class="fleet-map-overlay"
          :title="t('fleetMap.emptyApi')"
          :hint="t('fleetMap.emptyApiHint')"
        >
          <template #icon><Icon name="route" :size="20" /></template>
        </EmptyState>

        <EmptyState
          v-else-if="state === 'ready' && !visible.length"
          class="fleet-map-overlay"
          :title="t('fleetMap.noMatch')"
          :hint="t('fleetMap.noMatchHint')"
        >
          <template #icon><Icon name="pin" :size="20" /></template>
        </EmptyState>

        <EmptyState
          v-else-if="state === 'ready' && visible.length && !liveCount"
          class="fleet-map-overlay"
          :title="t('fleetMap.noneLive')"
          :hint="t('fleetMap.noneLiveHint')"
        >
          <template #icon><Icon name="pin" :size="20" /></template>
        </EmptyState>

        <div v-else-if="state === 'loading' && !rows.length" class="fleet-map-loading" aria-hidden="true" />
      </div>

      <aside class="fleet-signal-ledger" :aria-label="t('fleetMap.signalLedger')">
        <header>
          <p>{{ t("fleetMap.eyebrow") }}</p>
          <h2>{{ t("fleetMap.signalLedger") }}</h2>
          <span><bdi dir="auto">{{ t("fleetMap.subtitle", { live: liveCount, total: visible.length }) }}</bdi></span>
        </header>
        <ul>
          <li v-for="row in visible" :key="row.dispatch_trip">
            <span class="fleet-signal-copy">
              <strong><bdi dir="auto">{{ row.driver_name || t("common.none") }}</bdi></strong>
              <bdi dir="auto">{{ row.route_name }}</bdi>
              <bdi v-if="row.plate">{{ row.plate }}</bdi>
            </span>
            <Badge
              :label="positionLabel(row)"
              :theme="positionTheme(row)"
              variant="subtle"
              size="lg"
            />
          </li>
        </ul>
        <footer v-if="hasMore" class="fleet-map-more">
          <Button
            variant="outline"
            size="lg"
            :loading="moreBusy"
            :label="t('common.loadMore')"
            @click="loadMore()"
          />
        </footer>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Alert, Badge, Button, FormControl } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import MetricRibbon from "@shared/components/MetricRibbon.vue";
import { usePoll } from "@shared/usePoll.js";

import Icon from "../Icon.vue";
import { getActiveDriverPositions } from "../api.js";
import { createSequence } from "../fmt.js";
import {
  matchesDriverFilter,
  normalizeDriverFilter,
  uniqueDriverOptions,
} from "../mapFilters.js";
import { createMapFitPolicy } from "../mapFitPolicy.js";
import { TILE_ATTRIBUTION, TILE_URL, leaflet } from "../mapTiles.js";
import { mergePositionPages, nextPositionStart } from "../positionPages.js";
import { useI18n } from "@/i18n";

const { t, resourceErrorMessage } = useI18n();
const route = useRoute();
const router = useRouter();
const L = leaflet();
const hasLeaflet = Boolean(L);

const pages = ref([]);
const rows = computed(() => mergePositionPages(pages.value));
const state = ref("loading");
const error = ref("");
const moreBusy = ref(false);
const tilesDown = ref(false);
const mapEl = ref(null);
const seq = createSequence();
let map = null;
let markers = new Map();
let routeLines = new Map();
const fitPolicy = createMapFitPolicy();
const POLL_MS = 15000;
const PAGE_LENGTH = 50;

const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 10;

const driverFilter = computed(() => String(route.query.driver || ""));
const planFilter = computed(() => String(route.query.plan || ""));
const driverSelectValue = computed(() =>
  normalizeDriverFilter(rows.value, driverFilter.value),
);

function setFilter(key, value) {
  const query = { ...route.query };
  if (value) query[key] = value;
  else delete query[key];
  router.replace({ name: "map", query });
}

const visible = computed(() =>
  rows.value.filter(
    (row) =>
      matchesDriverFilter(row, driverFilter.value) &&
      (!planFilter.value || row.route_plan === planFilter.value),
  ),
);
const liveCount = computed(() => visible.value.filter((row) => row.has_position).length);
const staleCount = computed(() => visible.value.filter((row) => row.has_position && row.stale).length);
const noFixCount = computed(() => visible.value.filter((row) => !row.has_position).length);
const signalMetrics = computed(() => [
  { key: "live", label: t("common.live"), value: liveCount.value, tone: "success" },
  { key: "stale", label: t("fleetMap.staleShort"), value: staleCount.value, tone: "warning" },
  { key: "no-fix", label: t("fleetMap.noFix"), value: noFixCount.value },
]);
const positionLabel = (row) =>
  !row.has_position ? t("fleetMap.noFix") : row.stale ? t("fleetMap.staleShort") : t("common.live");
const positionTheme = (row) => (!row.has_position ? "gray" : row.stale ? "orange" : "green");

const driverOptions = computed(() => {
  return [
    { label: t("fleetMap.allDrivers"), value: "" },
    ...uniqueDriverOptions(rows.value),
  ];
});

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
const lastPage = computed(() =>
  [...pages.value].sort((a, b) => a.start - b.start).at(-1) || null,
);
const hasMore = computed(() => Boolean(lastPage.value?.has_more));

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
    html: '<span class="dm-pulse" data-motion="loop"></span><span class="dm-core" aria-hidden="true"></span>',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

function tooltipNode(...parts) {
  const node = document.createElement("span");
  node.textContent = parts.filter((part) => part != null && part !== "").join(" · ");
  return node;
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
      existing.line.setTooltipContent(tooltipNode(row.route_name));
      continue;
    }
    const onRoad = Boolean(row.path && row.path.length > 1);
    const line = L.polyline(latlngs, {
      weight: onRoad ? 5 : 3,
      opacity: onRoad ? 0.85 : 0.7,
      dashArray: onRoad ? null : "6 6",
    }).addTo(map);
    line.bindTooltip(tooltipNode(row.route_name), { sticky: true });
    const pins = points.map((stop, index) =>
      L.circleMarker([stop.lat, stop.lng], { radius: 5, weight: 2, fillOpacity: 1 })
        .bindTooltip(tooltipNode(index + 1, stop.stop_name), { direction: "top" })
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

function drawMarkers({ fit = fitPolicy.pending } = {}) {
  if (!map) return;
  const wanted = new Set();
  for (const row of visible.value) {
    if (!row.has_position) continue;
    wanted.add(row.dispatch_trip);
    const position = [row.lat, row.lng];
    const existing = markers.get(row.dispatch_trip);
    if (existing) {
      existing.setLatLng(position).setIcon(driverIcon(row));
      existing.setTooltipContent(tooltipNode(row.driver_name, row.route_name));
      continue;
    }
    const marker = L.marker(position, { icon: driverIcon(row) }).addTo(map);
    marker.bindTooltip(tooltipNode(row.driver_name, row.route_name), { direction: "top" });
    markers.set(row.dispatch_trip, marker);
  }
  for (const [key, marker] of markers) {
    if (wanted.has(key)) continue;
    map.removeLayer(marker);
    markers.delete(key);
  }
  drawRoutes();

  const drawn = [...markers.values(), ...[...routeLines.values()].map((r) => r.line)];
  if (fit && drawn.length > 1) {
    map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.2));
    fitPolicy.resolve(true);
  } else if (fit && drawn.length === 1) {
    map.fitBounds(L.featureGroup(drawn).getBounds().pad(0.4));
    fitPolicy.resolve(true);
  }
}

async function loadFirst() {
  const ticket = seq.next();
  state.value = "loading";
  try {
    const res = await getActiveDriverPositions(0, PAGE_LENGTH);
    if (!seq.isCurrent(ticket)) return;
    pages.value = [res];
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

async function loadMore() {
  if (!hasMore.value || moreBusy.value) return;
  const ticket = seq.next();
  moreBusy.value = true;
  try {
    const res = await getActiveDriverPositions(nextPositionStart(lastPage.value), PAGE_LENGTH);
    if (!seq.isCurrent(ticket)) return;
    pages.value = [...pages.value, res];
    state.value = "ready";
    error.value = "";
    await nextTick();
    ensureMap();
    drawMarkers();
  } catch (e) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(e, "fleetMap.loadError");
  } finally {
    moreBusy.value = false;
  }
}

async function refreshLoaded() {
  if (moreBusy.value) return;
  const starts = pages.value.length
    ? [...pages.value].sort((a, b) => a.start - b.start).map((page) => page.start)
    : [0];
  const ticket = seq.next();
  try {
    const refreshed = [];
    for (const start of starts) {
      const res = await getActiveDriverPositions(start, PAGE_LENGTH);
      if (!seq.isCurrent(ticket)) return;
      refreshed.push(res);
      if (!res.has_more) break;
    }
    pages.value = refreshed;
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

watch([driverFilter, planFilter], async () => {
  fitPolicy.request();
  await nextTick();
  drawMarkers({ fit: true });
});

usePoll(refreshLoaded, POLL_MS);
onMounted(loadFirst);

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
  display: grid;
  gap: clamp(var(--sp-4), 2vw, var(--sp-6));
}
.fleet-map-tools {
  padding-block: var(--sp-4);
  border-block-end: 1px solid var(--c-border-strong);
}
.fleet-map-filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: var(--sp-3);
}
.fleet-map-filters :deep(.space-y-1\.5) {
  flex: 1 1 12rem;
  min-inline-size: min(100%, 12rem);
}
.fleet-map-layout {
  min-inline-size: 0;
  display: grid;
  gap: var(--sp-5);
}
.fleet-map-canvas-wrap {
  position: relative;
  min-block-size: clamp(26rem, 64vh, 48rem);
  overflow: hidden;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius-lg);
  background: var(--c-surface);
}
.fleet-map-canvas,
.fleet-map-fallback {
  position: absolute;
  inset: 0;
}
.fleet-map-canvas {
  background: var(--c-surface);
}
.fleet-map-fallback {
  overflow-y: auto;
  padding: var(--sp-5);
}
.fleet-map-coordinates {
  list-style: none;
  margin: var(--sp-4) 0 0;
  padding: 0;
  display: grid;
  font-size: var(--fs-sm);
}
.fleet-map-coordinates li {
  display: grid;
  grid-template-columns: minmax(8rem, 1fr) minmax(8rem, 1fr) auto;
  gap: var(--sp-2);
  padding-block: var(--sp-3);
  border-block-end: 1px solid var(--c-border);
}
.fleet-map-tile-note {
  position: absolute;
  inset-block-start: var(--sp-3);
  inset-inline: var(--sp-3);
  z-index: 450;
}
.fleet-map-overlay {
  position: absolute;
  inset-block-start: 40%;
  inset-inline-start: 50%;
  translate: -50% -50%;
  inline-size: min(23rem, 84%);
  padding: var(--sp-4);
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  z-index: 460;
}
.fleet-map-loading {
  position: absolute;
  inset: 0;
  background: var(--c-surface-2);
  animation: signal-loading 1.2s ease-in-out infinite alternate;
}
.fleet-signal-ledger {
  min-inline-size: 0;
  border-block: 1px solid var(--c-border-strong);
}
.fleet-signal-ledger header {
  padding-block: var(--sp-4);
  border-block-end: 1px solid var(--c-border);
}
.fleet-signal-ledger header p,
.fleet-signal-ledger header h2,
.fleet-signal-ledger header span {
  margin: 0;
}
.fleet-signal-ledger header p {
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  text-transform: uppercase;
}
.fleet-signal-ledger header h2 {
  margin-block-start: var(--sp-1);
  font-size: var(--fs-h2);
}
.fleet-signal-ledger header span {
  display: block;
  margin-block-start: var(--sp-1);
  color: var(--c-muted);
  font-family: var(--font-serif);
}
.fleet-signal-ledger ul {
  max-block-size: 36rem;
  overflow-y: auto;
  margin: 0;
  padding: 0;
  list-style: none;
}
.fleet-signal-ledger li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  min-block-size: 4.75rem;
  padding-block: var(--sp-3);
  border-block-end: 1px solid var(--c-border);
}
.fleet-map-more {
  display: flex;
  justify-content: center;
  padding-block: var(--sp-4);
}
.fleet-signal-copy {
  min-inline-size: 0;
  display: grid;
  gap: 2px;
}
.fleet-signal-copy span,
.fleet-signal-copy bdi {
  color: var(--c-muted);
  font-size: var(--fs-xs);
}
@keyframes signal-loading {
  from { opacity: 0.55; }
  to { opacity: 1; }
}
@media (min-width: 70rem) {
  .fleet-map-layout {
    grid-template-columns: minmax(0, 1fr) minmax(17rem, 0.34fr);
  }
}
@media (max-width: 34rem) {
  .fleet-map-filters > * {
    inline-size: 100%;
  }
  .fleet-map-coordinates li {
    grid-template-columns: 1fr;
  }
}
@media (prefers-reduced-motion: reduce) {
  .fleet-map-loading {
    animation: none;
  }
}
</style>
