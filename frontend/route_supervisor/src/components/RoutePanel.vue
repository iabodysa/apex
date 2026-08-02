<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- The ordered stops of the selected plan as a vertical timeline. Self-fetches
     get_route_stops (the same _ordered_stops the driver/worker apps use), so sequence,
     planned times, expected passengers and Habitat housing pickups match everywhere. -->
<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("route.title") }}</h2>
        <p class="panel-sub">{{ t("route.subtitle") }}</p>
      </div>
    </header>

    <EmptyState v-if="state === 'error'" :title="error || t('route.loadError')">
      <template #icon><Icon name="triangle-alert" :size="20" :stroke-width="1.6" /></template>
      <template #action>
        <button class="soft-btn" @click="load()">{{ t("common.retry") }}</button>
      </template>
    </EmptyState>

    <div v-else-if="state === 'loading' && !data" class="skeleton-bar" />

    <EmptyState v-else-if="data && !data.stops.length" :title="t('route.empty')">
      <template #icon><Icon name="route" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <ol v-else-if="data" class="timeline">
      <li v-for="(s, i) in data.stops" :key="i" class="tl-item">
        <div class="tl-marker">
          <span class="tl-seq">{{ s.sequence || i + 1 }}</span>
        </div>
        <div class="tl-card">
          <div class="tl-top">
            <span class="tl-name">{{ s.stop_name }}</span>
            <span v-if="s.planned_time" class="tl-time"><Icon name="clock" :size="13" /> {{ s.planned_time }}</span>
          </div>
          <div class="tl-meta">
            <span v-if="s.location" class="tl-loc"><Icon name="pin" :size="13" /> {{ s.location }}</span>
            <span v-if="s.expected_passengers" class="tl-pax"><Icon name="user" :size="13" /> {{ t("route.passengers", { n: s.expected_passengers }) }}</span>
          </div>
          <a v-if="s.pickup && s.pickup.building_name" class="tl-housing"
             :href="s.pickup.google_maps_url || null" :target="s.pickup.google_maps_url ? '_blank' : null" rel="noopener">
            <Icon name="building" :size="13" /> {{ t("route.housing") }}: {{ s.pickup.building_name }}
          </a>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { ref, watch, onMounted } from "vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../Icon.vue";
import { useI18n } from "../i18n";
import { getRouteStops } from "../api.js";

const props = defineProps({ planName: { type: String, default: null } });
const { t, resourceErrorMessage } = useI18n();
const data = ref(null);
const state = ref("idle");
const error = ref("");

async function load() {
  if (!props.planName) return;
  if (!data.value) state.value = "loading";
  try {
    data.value = await getRouteStops(props.planName);
    state.value = "ready";
    error.value = "";
  } catch (e) {
    state.value = "error";
    error.value = resourceErrorMessage(e, "route.loadError");
  }
}

watch(
  () => props.planName,
  () => {
    data.value = null;
    load();
  },
);
onMounted(load);
</script>
