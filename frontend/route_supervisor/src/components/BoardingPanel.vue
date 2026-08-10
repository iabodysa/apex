<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="boarding-panel">
    <header class="section-heading section-heading-row">
      <div>
        <p>{{ t("boarding.eyebrow") }}</p>
        <h3>{{ t("boarding.title") }}</h3>
        <span>{{ t("boarding.subtitle") }}</span>
      </div>
      <Button
        v-if="tripName"
        variant="outline"
        size="lg"
        :aria-label="t('common.refresh')"
        :loading="state === 'loading' && Boolean(data)"
        @click="load()"
      >
        <template #icon><Icon name="refresh" :size="17" /></template>
      </Button>
    </header>

    <AsyncBoundary
      :state="boundaryState"
      :title="boundaryTitle"
      :message="boundaryMessage"
      :retry-label="t('common.retry')"
      @retry="load()"
    >
      <div class="boarding-progress">
        <div class="boarding-count">
          <strong><bdi>{{ data.boarding.boarded }}</bdi></strong>
          <span><bdi dir="auto">{{ t("boarding.of", { boarded: data.boarding.boarded, expected: data.boarding.expected }) }}</bdi></span>
        </div>
        <div class="boarding-progress-line">
          <Progress :value="ratio" size="md" />
          <Badge
            :label="tripStatusLabel"
            :theme="tripStatusTheme"
            variant="subtle"
            size="lg"
          />
        </div>
        <p v-if="!data.boarding.has_manifest" class="boarding-note">{{ t("boarding.noManifest") }}</p>
      </div>

      <MetricRibbon :metrics="boardingMetrics" />

      <section v-if="data.workers.length" class="passenger-ledger">
        <h4>{{ t("boarding.workers") }}</h4>
        <ul>
          <li v-for="worker in data.workers" :key="worker.employee">
            <span><Icon name="user" :size="15" /> <bdi dir="auto">{{ worker.employee_name }}</bdi></span>
            <Badge
              :label="t('workerStatus.' + worker.status)"
              :theme="workerTheme(worker.status)"
              variant="subtle"
              size="lg"
            />
          </li>
        </ul>
      </section>
    </AsyncBoundary>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, Progress } from "frappe-ui";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import MetricRibbon from "@shared/components/MetricRibbon.vue";
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
const tripStatusLabel = computed(() => {
  const status = data.value?.status;
  if (!status) return t("common.none");
  const key = "tripStatus." + status;
  const label = t(key);
  return label === key ? status : label;
});
const tripStatusTheme = computed(
  () => ({ Planned: "blue", Dispatched: "orange", Completed: "green", Cancelled: "red" })[data.value?.status] || "gray",
);
const boardingMetrics = computed(() =>
  data.value
    ? [
        { key: "boarded", label: t("boarding.boarded"), value: data.value.boarding.boarded, tone: "success" },
        { key: "claimed", label: t("boarding.claimed"), value: data.value.boarding.claimed, tone: "info" },
        { key: "pending", label: t("boarding.pending"), value: data.value.boarding.pending, tone: "warning" },
        {
          key: "absent",
          label: t("boarding.absent"),
          value: data.value.boarding.absent + data.value.boarding.rejected,
          tone: "danger",
        },
      ]
    : [],
);
const boundaryState = computed(() => {
  if (!props.tripName) return "empty";
  if (state.value === "error") return "error";
  if (state.value === "loading" && !data.value) return "loading";
  return data.value ? "ready" : "loading";
});
const boundaryTitle = computed(() =>
  !props.tripName ? t("boarding.noTrip") : t("boarding.loadError"),
);
const boundaryMessage = computed(() => (state.value === "error" ? error.value : ""));

const workerTheme = (status) =>
  ({
    Boarded: "green",
    [BOARDING.WORKER_CLAIMED]: "blue",
    Pending: "orange",
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
    const response = await getTripBoarding(props.tripName);
    if (!seq.isCurrent(ticket)) return;
    data.value = response;
    state.value = "ready";
    error.value = "";
  } catch (exception) {
    if (!seq.isCurrent(ticket)) return;
    state.value = "error";
    error.value = resourceErrorMessage(exception, "boarding.loadError");
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
