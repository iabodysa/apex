<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Live driver map. Polls get_trip_driver_position (the driver-portal telematics stamped
     on the Dispatch Trip) and moves a marker on an OpenStreetMap/Leaflet map. Degrades
     gracefully at every failure boundary: no trip -> prompt; no GPS fix yet -> a waiting
     state (never a marker at 0,0); Leaflet unavailable -> a plain coordinate readout. A
     stale fix dims the marker so a frozen position never reads as live. -->
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

    <div v-if="!tripName" class="empty">
      <Icon name="truck" :size="34" :stroke-width="1.6" />
      <p>{{ t("map.noTrip") }}</p>
    </div>

    <div v-else-if="state === 'error'" class="empty">
      <Icon name="triangle-alert" :size="30" :stroke-width="1.6" />
      <p>{{ error || t("map.loadError") }}</p>
      <button class="soft-btn" @click="load()">{{ t("common.retry") }}</button>
    </div>

    <template v-else>
      <!-- Driver / vehicle strip -->
      <div v-if="data" class="map-info">
        <span><Icon name="user" :size="14" /> {{ t("map.driver") }}: <b>{{ data.driver_name || t("common.none") }}</b></span>
        <span><Icon name="truck" :size="14" /> {{ t("map.vehicle") }}: <b>{{ data.plate || t("common.none") }}</b></span>
        <span v-if="data.has_position" class="upd"><Icon name="clock" :size="13" /> {{ t("map.updated", { age: age }) }}</span>
      </div>

      <!-- Map (Leaflet available) -->
      <div v-if="hasLeaflet" class="map-wrap">
        <div ref="mapEl" class="map-canvas" :class="{ dim: data && data.stale }" />
        <div v-if="data && !data.has_position" class="map-overlay">
          <Icon name="pin" :size="30" :stroke-width="1.6" />
          <p class="ov-title">{{ t("map.noFix") }}</p>
          <p class="ov-hint">{{ t("map.noFixHint") }}</p>
        </div>
      </div>

      <!-- Leaflet unavailable: coordinate fallback -->
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
const mapEl = ref(null);
let map = null;
let marker = null;
let timer = null;
const POLL_MS = 10000;

// Default view (Riyadh) until the first fix lands.
const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 11;

const age = computed(() => ageLabel(data.value?.age_seconds, t));

function ensureMap() {
  if (!hasLeaflet || map || !mapEl.value) return;
  map = L.map(mapEl.value, { zoomControl: true, attributionControl: true }).setView(
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
  );
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap",
  }).addTo(map);
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
    if (res.has_position && hasLeaflet) {
      await nextTick();
      ensureMap();
      updateMarker(res.lat, res.lng);
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
// Leaflet mis-sizes when its container was hidden (inactive tab); fix on activation.
watch(
  () => props.active,
  async (a) => {
    if (a) {
      await load();
      await nextTick();
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
