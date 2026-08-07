<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("boarding.title") }}</h2>
        <p class="panel-sub">{{ t("boarding.subtitle") }}</p>
      </div>
      <button v-if="tripName" class="ghost-btn" :title="t('common.refresh')" @click="load()">
        <Icon name="refresh" :size="16" />
      </button>
    </header>

    <EmptyState v-if="!tripName" :title="t('boarding.noTrip')">
      <template #icon><Icon name="bus" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <EmptyState v-else-if="state === 'error'" :title="error || t('boarding.loadError')">
      <template #icon><Icon name="triangle-alert" :size="20" :stroke-width="1.6" /></template>
      <template #action>
        <button class="soft-btn" @click="load()">{{ t("common.retry") }}</button>
      </template>
    </EmptyState>

    <div v-else-if="state === 'loading' && !data" class="skeleton-bar" />

    <div v-else-if="data" class="boarding-body">
      <div class="progress-hero">
        <div class="ring" :style="ringStyle" role="img" :aria-label="ofLabel">
          <div class="ring-inner">
            <span class="ring-num">{{ data.boarding.boarded }}</span>
            <span class="ring-den">/ {{ data.boarding.expected || "—" }}</span>
          </div>
        </div>
        <div class="progress-meta">
          <div class="of-line">{{ ofLabel }}</div>
          <div class="trip-status">
            <span class="dot" :class="'st-' + (data.status || '').toLowerCase()" />
            {{ t("boarding.tripStatus") }}: {{ tripStatusLabel }}
          </div>
          <p v-if="!data.boarding.has_manifest" class="hint">{{ t("boarding.noManifest") }}</p>
        </div>
      </div>

      <div class="chips">
        <div class="chip chip-ok"><b>{{ data.boarding.boarded }}</b>{{ t("boarding.boarded") }}</div>
        <div class="chip chip-claim"><b>{{ data.boarding.claimed }}</b>{{ t("boarding.claimed") }}</div>
        <div class="chip chip-wait"><b>{{ data.boarding.pending }}</b>{{ t("boarding.pending") }}</div>
        <div class="chip chip-bad"><b>{{ data.boarding.absent + data.boarding.rejected }}</b>{{ t("boarding.absent") }}</div>
      </div>

      <div v-if="data.workers.length" class="worker-list">
        <h3 class="mini-title">{{ t("boarding.workers") }}</h3>
        <ul>
          <li v-for="w in data.workers" :key="w.employee" class="worker-row">
            <span class="w-name"><Icon name="user" :size="15" /> {{ w.employee_name }}</span>
            <span class="w-pill" :class="pillClass(w.status)">{{ t("workerStatus." + w.status) }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { BOARDING } from "@shared/statusVocabularies";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../Icon.vue";
import { useI18n } from "../i18n";
import { getTripBoarding } from "../api.js";
import { pct } from "../fmt.js";

const props = defineProps({
  tripName: { type: String, default: null },
  active: { type: Boolean, default: false },
});

const { t, resourceErrorMessage } = useI18n();
const data = ref(null);
const state = ref("idle");
const error = ref("");
let timer = null;
const POLL_MS = 15000;

const ofLabel = computed(() =>
  data.value
    ? t("boarding.of", { boarded: data.value.boarding.boarded, expected: data.value.boarding.expected })
    : "",
);
const tripStatusLabel = computed(() => {
  const s = data.value && data.value.status;
  if (!s) return t("common.none");
  const key = "tripStatus." + s;
  const label = t(key);
  return label === key ? s : label;
});
const ringStyle = computed(() => {
  const p = data.value ? pct(data.value.boarding.boarded, data.value.boarding.expected) : 0;
  return { "--p": p + "%" };
});

function pillClass(status) {
  return (
    {
      Boarded: "w-ok",
      [BOARDING.WORKER_CLAIMED]: "w-claim",
      Pending: "w-wait",
      [BOARDING.DRIVER_REJECTED]: "w-bad",
      Absent: "w-bad",
    }[status] || "w-wait"
  );
}

async function load() {
  if (!props.tripName) {
    data.value = null;
    return;
  }
  if (!data.value) state.value = "loading";
  try {
    data.value = await getTripBoarding(props.tripName);
    state.value = "ready";
    error.value = "";
  } catch (e) {
    state.value = "error";
    error.value = resourceErrorMessage(e, "boarding.loadError");
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
    load();
  },
);
watch(
  () => props.active,
  (a) => {
    if (a) load();
  },
);
onMounted(() => {
  load();
  start();
});
onUnmounted(stop);
</script>
