<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("boarding.title") }}</h2>
        <p class="panel-sub">{{ t("boarding.subtitle") }}</p>
      </div>
      <Button
        v-if="tripName"
        variant="outline"
        size="lg"
        :label="t('common.refresh')"
        :loading="state === 'loading' && Boolean(data)"
        @click="load()"
      >
        <template #icon><Icon name="refresh" :size="17" /></template>
      </Button>
    </header>

    <EmptyState v-if="!tripName" :title="t('boarding.noTrip')">
      <template #icon><Icon name="bus" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <LoadError
      v-else-if="state === 'error'"
      :title="t('boarding.loadError')"
      :detail="error"
      :hint="t('list.loadErrorHint')"
      :retry-label="t('common.retry')"
      @retry="load()"
    />

    <div v-else-if="state === 'loading' && !data" class="skeleton-bar" aria-hidden="true" />

    <div v-else-if="data" class="boarding-body">
      <div class="progress-hero">
        <div class="count-hero">
          <span class="count-num">{{ data.boarding.boarded }}</span>
          <span class="count-den">/ {{ data.boarding.expected || t("common.none") }}</span>
        </div>
        <div class="progress-meta">
          <div class="of-line">{{ ofLabel }}</div>
          <Progress class="of-bar" :value="ratio" size="md" />
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
        <div class="chip chip-bad">
          <b>{{ data.boarding.absent + data.boarding.rejected }}</b>{{ t("boarding.absent") }}
        </div>
      </div>

      <div v-if="data.workers.length" class="worker-list">
        <h3 class="mini-title">{{ t("boarding.workers") }}</h3>
        <ul>
          <li v-for="w in data.workers" :key="w.employee" class="worker-row">
            <span class="w-name"><Icon name="user" :size="15" /> {{ w.employee_name }}</span>
            <Badge :theme="workerTheme(w.status)" size="sm" :label="t('workerStatus.' + w.status)" />
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, Progress } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import { usePoll } from "@shared/usePoll.js";
import { BOARDING } from "@shared/statusVocabularies";

import Icon from "../Icon.vue";
import { getTripBoarding } from "../api.js";
import { createSequence, pct } from "../fmt.js";
import { useI18n } from "@/i18n";

const props = defineProps({
  tripName: { type: String, default: null },
  active: { type: Boolean, default: false },
});

const { t, resourceErrorMessage } = useI18n();
const data = ref(null);
const state = ref("idle");
const error = ref("");
const seq = createSequence();
const POLL_MS = 15000;

const ratio = computed(() =>
  data.value ? pct(data.value.boarding.boarded, data.value.boarding.expected) : 0,
);
const ofLabel = computed(() =>
  data.value
    ? t("boarding.of", {
        boarded: data.value.boarding.boarded,
        expected: data.value.boarding.expected,
      })
    : "",
);
const tripStatusLabel = computed(() => {
  const s = data.value && data.value.status;
  if (!s) return t("common.none");
  const key = "tripStatus." + s;
  const label = t(key);
  return label === key ? s : label;
});

const workerTheme = (status) =>
  ({
    Boarded: "green",
    [BOARDING.WORKER_CLAIMED]: "blue",
    Pending: "gray",
    [BOARDING.DRIVER_REJECTED]: "red",
    Absent: "red",
  })[status] || "gray";

async function load() {
  if (!props.tripName) {
    data.value = null;
    return;
  }
  if (!data.value) state.value = "loading";
  const ticket = seq.next();
  try {
    const res = await getTripBoarding(props.tripName);
    /* The manual refresh and the 15 s poll can be in flight together; only the newest answer
       is allowed to repaint, or a slow one lands on top of a fresher count. */
    if (!seq.isCurrent(ticket)) return;
    data.value = res;
    state.value = "ready";
    error.value = "";
  } catch (e) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(e, "boarding.loadError");
  }
}

watch(
  () => props.tripName,
  () => {
    data.value = null;
    load();
  },
  { immediate: true },
);

usePoll(() => {
  if (props.active && props.tripName) return load();
}, POLL_MS);
</script>
