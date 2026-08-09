<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="driver-map" :class="{ 'is-compact': compact }">
    <header class="section-heading section-heading-row">
      <div>
        <p>{{ t("map.eyebrow") }}</p>
        <h3>{{ t("map.title") }}</h3>
        <span v-if="!compact">{{ t("map.subtitle") }}</span>
      </div>
      <StatusLabel
        v-if="data"
        :label="positionLabel"
        :tone="data.has_position ? (data.stale ? 'warning' : 'success') : 'neutral'"
      />
    </header>

    <EmptyState v-if="!tripName" :title="t('map.noTrip')">
      <template #icon><Icon name="truck" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <LoadError
      v-else-if="state === 'error'"
      :title="t('map.loadError')"
      :detail="error"
      :hint="t('list.loadErrorHint')"
      :retry-label="t('common.retry')"
      @retry="load()"
    />

    <div v-else-if="state === 'loading' && !data" class="map-loading" aria-hidden="true" />

    <template v-else>
      <div v-if="data" class="map-info">
        <span><Icon name="user" :size="14" /> {{ t("map.driver") }}: <b>{{ data.driver_name || t("common.none") }}</b></span>
        <span><Icon name="truck" :size="14" /> {{ t("map.vehicle") }}: <b><bdi>{{ data.plate || t("common.none") }}</bdi></b></span>
        <span v-if="data.has_position" class="upd">
          <Icon name="clock" :size="13" /> {{ t("map.updated", { age }) }}
        </span>
      </div>

      <div v-if="hasLeaflet" class="map-wrap">
        <div ref="mapEl" class="map-canvas" :class="{ dim: data && data.stale }" />
        <Alert
          v-if="tilesDown"
          class="tile-note"
          theme="yellow"
          :title="t('map.tilesUnavailable')"
          :dismissable="false"
        />
        <div v-if="data && !data.has_position" class="map-overlay">
          <Icon name="pin" :size="30" :stroke-width="1.6" />
          <p class="ov-title">{{ t("map.noFix") }}</p>
          <p class="ov-hint">{{ t("map.noFixHint") }}</p>
        </div>
      </div>

      <div v-else class="map-fallback">
        <Alert theme="yellow" :title="t('map.unavailable')" :dismissable="false" />
        <div v-if="data && data.has_position" class="fb-coords">
          <span><Icon name="pin" :size="15" /> <bdi>{{ data.lat.toFixed(6) }}, {{ data.lng.toFixed(6) }}</bdi></span>
        </div>
        <EmptyState v-else :title="t('map.noFix')" :hint="t('map.noFixHint')">
          <template #icon><Icon name="pin" :size="20" :stroke-width="1.6" /></template>
        </EmptyState>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { Alert } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import { usePoll } from "@shared/usePoll.js";

import Icon from "../Icon.vue";
import { getTripDriverPosition } from "../api.js";
import { createSequence, ageLabel } from "../fmt.js";
import { TILE_ATTRIBUTION, TILE_URL, leaflet } from "../mapTiles.js";
import { useI18n } from "@/i18n";

const props = defineProps({
  tripName: { type: String, default: null },
  active: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
});

const { t, resourceErrorMessage } = useI18n();
const L = leaflet();
const hasLeaflet = Boolean(L);

const data = ref(null);
const state = ref("loading");
const error = ref("");
const tilesDown = ref(false);
const mapEl = ref(null);
const seq = createSequence();
let map = null;
let marker = null;
const POLL_MS = 10000;

const DEFAULT_CENTER = [24.7136, 46.6753];
const DEFAULT_ZOOM = 11;

const age = computed(() => ageLabel(data.value?.age_seconds, t));
const positionLabel = computed(() => {
  if (!data.value?.has_position) return t("map.noFixShort");
  return data.value.stale ? t("map.stale", { age: age.value }) : t("common.live");
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

/* A marker for a bus: the glyph is decorative and the position is what carries meaning, so the
   readout beside the map repeats it for anyone who cannot see the pin. */
function busIcon() {
  return L.divIcon({
    className: "driver-marker",
    html: '<span class="dm-pulse" data-motion="loop"></span><span class="dm-core" aria-hidden="true"></span>',
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
  if (!data.value) state.value = "loading";
  const ticket = seq.next();
  try {
    const res = await getTripDriverPosition(props.tripName);
    if (!seq.isCurrent(ticket)) return;
    data.value = res;
    state.value = "ready";
    error.value = "";
    if (hasLeaflet) {
      await nextTick();
      ensureMap();
      if (res.has_position) updateMarker(res.lat, res.lng);
    }
  } catch (e) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(e, "map.loadError");
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
  { immediate: true },
);

watch(
  () => props.active,
  async (on) => {
    if (!on) return;
    await load();
    await nextTick();
    ensureMap();
    if (map) map.invalidateSize();
  },
);

usePoll(() => {
  if (props.active && props.tripName) return load();
}, POLL_MS);

onUnmounted(() => {
  if (map) {
    map.remove();
    map = null;
  }
  marker = null;
});
</script>
