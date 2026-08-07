<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel map-panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("map.title") }}</h2>
        <p class="panel-sub">{{ t("map.subtitle") }}</p>
      </div>
      <div v-if="data && data.has_position" class="live-badge" :class="{ stale: data.stale }">
        <span class="live-dot" />
        {{ data.stale ? t("map.stale", { age: age }) : t("common.live") }}
      </div>
    </header>

    <EmptyState v-if="!tripName" :title="t('map.noTrip')">
      <template #icon><Icon name="truck" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <EmptyState v-else-if="state === 'error'" :title="error || t('map.loadError')">
      <template #icon><Icon name="triangle-alert" :size="20" :stroke-width="1.6" /></template>
      <template #action>
        <button class="soft-btn" @click="load()">{{ t("common.retry") }}</button>
      </template>
    </EmptyState>

    <template v-else>
      <div v-if="data" class="map-info">
        <span><Icon name="user" :size="14" /> {{ t("map.driver") }}: <b>{{ data.driver_name || t("common.none") }}</b></span>
        <span><Icon name="truck" :size="14" /> {{ t("map.vehicle") }}: <b>{{ data.plate || t("common.none") }}</b></span>
        <span v-if="data.has_position" class="upd"><Icon name="clock" :size="13" /> {{ t("map.updated", { age: age }) }}</span>
      </div>

      <div v-if="hasLeaflet" class="map-wrap">
        <div ref="mapEl" class="map-canvas" :class="{ dim: data && data.stale }" />
        <p v-if="tilesDown" class="tile-note">{{ t("map.tilesUnavailable") }}</p>
        <div v-if="data && !data.has_position" class="map-overlay">
          <Icon name="pin" :size="30" :stroke-width="1.6" />
          <p class="ov-title">{{ t("map.noFix") }}</p>
          <p class="ov-hint">{{ t("map.noFixHint") }}</p>
        </div>
      </div>

      <div v-else class="map-fallback">
        <p class="fb-note">{{ t("map.unavailable") }}</p>
        <div v-if="data && data.has_position" class="fb-coords">
          <span><Icon name="pin" :size="15" /> {{ data.lat.toFixed(6) }}, {{ data.lng.toFixed(6) }}</span>
        </div>
        <div v-else class="empty small">
          <Icon name="pin" :size="26" :stroke-width="1.6" />
          <p>{{ t("map.noFix") }}</p>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../Icon.vue";
import { useI18n } from "../i18n";
import { getTripDriverPosition } from "../api.js";
import { ageLabel } from "../fmt.js";

const props = defineProps({
  tripName: { type: String, default: null },
  active: { type: Boolean, default: false },
});

const { t, resourceErrorMessage } = useI18n();
const L = typeof window !== "undefined" ? window.L : undefined;
const hasLeaflet = !!L;

const data = ref(null);
const state = ref("idle");
const error = ref("");
const tilesDown = ref(false);
const mapEl = ref(null);
let map = null;
let marker = null;
let timer = null;
const POLL_MS = 10000;

const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 11;

const DEFAULT_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_TILE_ATTRIBUTION = "© OpenStreetMap";
const tileConfig = (typeof window !== "undefined" && window.apex_map_tiles) || {};
const TILE_URL = tileConfig.url || DEFAULT_TILE_URL;
const TILE_ATTRIBUTION = tileConfig.attribution || DEFAULT_TILE_ATTRIBUTION;

const age = computed(() => ageLabel(data.value?.age_seconds, t));

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

function busIcon() {
  return L.divIcon({
    className: "driver-marker",
    html: '<span class="dm-pulse"></span><span class="dm-core">🚌</span>',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

function updateMarker(lat, lng) {
  if (!hasLeaflet || !map) return;
  const ll = [lat, lng];
  if (!marker) {
    marker = L.marker(ll, { icon: busIcon() }).addTo(map);
    map.setView(ll, 14);
  } else {
    marker.setLatLng(ll);
    map.panTo(ll);
  }
}

async function load() {
  if (!props.tripName) {
    data.value = null;
    return;
  }
  try {
    const res = await getTripDriverPosition(props.tripName);
    data.value = res;
    state.value = "ready";
    error.value = "";
    if (hasLeaflet) {
      await nextTick();
      ensureMap();
      if (res.has_position) updateMarker(res.lat, res.lng);
    }
  } catch (e) {
    state.value = "error";
    error.value = resourceErrorMessage(e, "map.loadError");
  }
}

function tick() {
  if (document.hidden || !props.active || !props.tripName) return;
  load();
}
function start() {
  if (timer) return;
  timer = setInterval(tick, POLL_MS);
}
function stop() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

watch(
  () => props.tripName,
  () => {
    data.value = null;
    if (marker && map) {
      map.removeLayer(marker);
      marker = null;
    }
    load();
  },
);
watch(
  () => props.active,
  async (a) => {
    if (a) {
      await load();
      await nextTick();
      ensureMap();
      if (map) map.invalidateSize();
    }
  },
);

onMounted(() => {
  load();
  start();
});
onUnmounted(() => {
  stop();
  if (map) {
    map.remove();
    map = null;
  }
});
</script>
