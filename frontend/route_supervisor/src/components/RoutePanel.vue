<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("route.title") }}</h2>
        <p class="panel-sub">{{ t("route.subtitle") }}</p>
      </div>
    </header>

    <LoadError
      v-if="state === 'error'"
      :title="t('route.loadError')"
      :detail="error"
      :hint="t('list.loadErrorHint')"
      :retry-label="t('common.retry')"
      @retry="load()"
    />

    <div v-else-if="state === 'loading' && !data" class="skeleton-bar" aria-hidden="true" />

    <EmptyState v-else-if="data && !data.stops.length" :title="t('route.empty')">
      <template #icon><Icon name="route" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <ol v-else-if="data" class="timeline">
      <li v-for="(s, i) in data.stops" :key="s.sequence != null ? s.sequence : i" class="tl-item">
        <div class="tl-marker">
          <span class="tl-seq">{{ s.sequence || i + 1 }}</span>
        </div>
        <div class="tl-card">
          <div class="tl-top">
            <span class="tl-name">{{ s.stop_name }}</span>
            <span v-if="s.planned_time" class="tl-time">
              <Icon name="clock" :size="13" /> <bdi>{{ s.planned_time }}</bdi>
            </span>
          </div>
          <div class="tl-meta">
            <span v-if="s.location" class="tl-loc"><Icon name="pin" :size="13" /> {{ s.location }}</span>
            <span v-if="s.expected_passengers" class="tl-pax">
              <Icon name="user" :size="13" /> {{ t("route.passengers", { n: s.expected_passengers }) }}
            </span>
          </div>
          <a
            v-if="s.pickup && s.pickup.building_name && s.pickup.google_maps_url"
            class="tl-housing"
            :href="s.pickup.google_maps_url"
            target="_blank"
            rel="noopener"
          >
            <Icon name="building" :size="13" /> {{ t("route.housing") }}: {{ s.pickup.building_name }}
          </a>
          <span v-else-if="s.pickup && s.pickup.building_name" class="tl-housing tl-housing-flat">
            <Icon name="building" :size="13" /> {{ t("route.housing") }}: {{ s.pickup.building_name }}
          </span>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

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

async function load() {
  if (!props.planName) return;
  if (!data.value) state.value = "loading";
  const ticket = seq.next();
  try {
    const res = await getRouteStops(props.planName);
    if (!seq.isCurrent(ticket)) return;
    data.value = res;
    state.value = "ready";
    error.value = "";
  } catch (e) {
    if (!seq.isCurrent(ticket)) return;
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
  { immediate: true },
);
</script>
