<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="route-panel">
    <header class="section-heading">
      <p>{{ t("route.eyebrow") }}</p>
      <h3>{{ t("route.title") }}</h3>
      <span>{{ t("route.subtitle") }}</span>
    </header>

    <AsyncBoundary
      :state="boundaryState"
      :title="boundaryTitle"
      :message="error"
      :retry-label="t('common.retry')"
      @retry="load()"
    >
      <ol class="stop-ledger">
        <li v-for="(stop, index) in data.stops" :key="stop.sequence != null ? stop.sequence : index">
          <span class="stop-sequence"><bdi>{{ stop.sequence || index + 1 }}</bdi></span>
          <span class="stop-copy">
            <strong><bdi dir="auto">{{ stop.stop_name }}</bdi></strong>
            <span class="stop-meta">
              <span v-if="stop.location"><Icon name="pin" :size="13" /> <bdi dir="auto">{{ stop.location }}</bdi></span>
              <span v-if="stop.expected_passengers">
                <Icon name="user" :size="13" /> <bdi dir="auto">{{ t("route.passengers", { n: stop.expected_passengers }) }}</bdi>
              </span>
            </span>
            <a
              v-if="stop.pickup?.building_name && stop.pickup?.google_maps_url"
              :href="stop.pickup.google_maps_url"
              target="_blank"
              rel="noopener"
            >
              <Icon name="building" :size="13" /> {{ t("route.housing") }}: <bdi dir="auto">{{ stop.pickup.building_name }}</bdi>
            </a>
            <span v-else-if="stop.pickup?.building_name" class="stop-building">
              <Icon name="building" :size="13" /> {{ t("route.housing") }}: <bdi dir="auto">{{ stop.pickup.building_name }}</bdi>
            </span>
          </span>
          <time v-if="stop.planned_time" class="stop-time">
            <Icon name="clock" :size="13" /> <bdi>{{ stop.planned_time }}</bdi>
          </time>
        </li>
      </ol>
    </AsyncBoundary>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";

import Icon from "../Icon.vue";
import { getRouteStops } from "../api.js";
import { createSequence } from "../fmt.js";
import { useI18n } from "@/i18n";

const props = defineProps({ planName: { type: String, default: null } });

const { t, resourceErrorMessage } = useI18n();
const data = ref(null);
const state = ref("idle");
const error = ref("");
const seq = createSequence();

const boundaryState = computed(() => {
  if (state.value === "error") return "error";
  if (state.value === "loading" || !data.value) return "loading";
  return data.value.stops.length ? "ready" : "empty";
});
const boundaryTitle = computed(() =>
  boundaryState.value === "empty" ? t("route.empty") : t("route.loadError"),
);

async function load() {
  if (!props.planName) return;
  if (!data.value) state.value = "loading";
  const ticket = seq.next();
  try {
    const response = await getRouteStops(props.planName);
    if (!seq.isCurrent(ticket)) return;
    data.value = response;
    state.value = "ready";
    error.value = "";
  } catch (exception) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(exception, "route.loadError");
  }
}

watch(
  () => props.planName,
  () => {
    data.value = null;
    load();
  },
  { immediate: true },
);
</script>
