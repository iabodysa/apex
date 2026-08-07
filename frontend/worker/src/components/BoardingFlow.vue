<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="bflow space-y-3">
    <div v-if="wrongBus" class="bflow-panel bflow-wrong">
      <div class="bflow-panel-head">
        <Icon name="alert" :size="22" class="shrink-0" />
        <span class="bflow-panel-title">{{ t("boarding.wrongBusTitle") }}</span>
      </div>
      <p v-if="wrongBus.correct_trip" class="bflow-line bflow-strong">
        {{ t("boarding.wrongBusYourTrip", { trip: correctTripLabel }) }}
      </p>
      <p v-if="wrongBus.correct_driver && wrongBus.correct_driver.name" class="bflow-line">
        {{ t("boarding.wrongBusYourDriver", { name: wrongBus.correct_driver.name }) }}
      </p>
      <p v-if="wrongBus.route" class="bflow-line bflow-muted">
        {{ t("boarding.wrongBusRoute", { route: wrongBus.route }) }}
      </p>
      <p class="bflow-line bflow-muted">{{ t("boarding.wrongBusHint") }}</p>
      <div v-if="correctDriverPhone" class="grid grid-cols-2 gap-3">
        <a :href="'tel:' + correctDriverPhone" class="btn btn-primary" style="text-decoration: none">
          <Icon name="phone" :size="18" /> {{ t("common.call") }}
        </a>
        <a :href="waLink(correctDriverPhone)" target="_blank" rel="noopener" class="btn btn-accent" style="text-decoration: none">
          <Icon name="message" :size="18" /> {{ t("common.whatsapp") }}
        </a>
      </div>
    </div>

    <template v-else>
      <div v-if="stale" class="bflow-stale" role="status">
        <Icon name="alert" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.stale") }}</p>
          <p class="bflow-muted">{{ t("boarding.staleHint") }}</p>
        </div>
      </div>

      <div v-if="driverArrived && !BOARDING_SETTLED.includes(status)" class="bflow-panel bflow-arrived">
        <div class="bflow-panel-head">
          <Icon name="bus" :size="20" class="shrink-0 rtl-flip" />
          <span class="bflow-panel-title">{{ t("boarding.arrivedTitle") }}</span>
        </div>
        <p class="bflow-line">{{ t("boarding.arrivedHint") }}</p>
      </div>

      <div v-if="departSecs !== null" class="bflow-panel bflow-departing">
        <div class="bflow-panel-head">
          <Icon name="bus" :size="20" class="shrink-0 rtl-flip" />
          <span class="bflow-panel-title">{{ t("boarding.departing") }}</span>
        </div>
        <p class="bflow-countdown">
          {{ departSecs > 0 ? t("boarding.departingIn", { s: departSecs }) : t("boarding.departingNow") }}
        </p>
      </div>

      <div v-if="status === BOARDING.BOARDED" class="bflow-status bflow-ok">
        <Icon name="check" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.boardedTitle") }}</p>
          <p class="bflow-muted">{{ t("boarding.boardedHint") }}</p>
        </div>
      </div>
      <div v-else-if="status === BOARDING.ABSENT" class="bflow-status bflow-danger">
        <Icon name="alert" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.absentTitle") }}</p>
          <p class="bflow-muted">{{ t("boarding.absentHint") }}</p>
        </div>
      </div>

      <BoardingWindow v-else-if="!canConfirm" :window="boardingWindow" />
      <button
        v-else
        class="btn btn-primary"
        :disabled="claim.loading || stale"
        @click="doClaim"
      >
        <Icon name="check" :size="18" />
        {{ claim.loading ? t("boarding.onBusSending") : t("boarding.onBus") }}
      </button>

      <p v-if="claimError" class="text-sm text-danger">{{ claimError }}</p>

      <template v-if="canRequestWait">
        <p v-if="waitCountdown !== null" class="bflow-wait-note">
          <Icon name="clock" :size="14" class="shrink-0" />
          {{ t("boarding.waitCountdown", { s: waitCountdown }) }}
        </p>
        <button
          class="btn btn-outline"
          :disabled="wait.loading || waitCapReached || stale"
          @click="doWait"
        >
          <Icon name="clock" :size="18" />
          {{ wait.loading ? t("boarding.waitSending") : t("boarding.waitForMe") }}
        </button>
        <p v-if="waitMax" class="bflow-wait-used">
          {{ waitCapReached ? t("boarding.waitCapReached") : t("boarding.waitRemaining", { n: waitCount, max: waitMax }) }}
        </p>
        <p v-if="waitError" class="text-sm text-danger">{{ waitError }}</p>
      </template>

      <button class="btn btn-outline" :disabled="passLoading" @click="openPass">
        <Icon name="card" :size="18" /> {{ t("boarding.view") }}
      </button>
      <p v-if="passError && !passData" class="text-sm text-muted">{{ t("boarding.none") }}</p>

      <BoardingPassOverlay
        v-if="passData"
        :open="passOpen"
        :pass="passData"
        :trip="trip"
        @close="passOpen = false"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, ref, onUnmounted, watch } from "vue";
import { BOARDING, BOARDING_SETTLED } from "@shared/statusVocabularies";
import { createResource } from "frappe-ui";
import Icon from "./Icon.vue";
import BoardingWindow from "./BoardingWindow.vue";
import BoardingPassOverlay from "./BoardingPassOverlay.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { TOKEN } from "../utils/token";
import { waLink } from "../utils/phone";

const { t } = useI18n();

const props = defineProps({
  trip: { type: Object, default: null },
  boarding: { type: Object, default: null },
  stale: { type: Boolean, default: false },
});

const hasTrip = computed(() => !!(props.boarding && props.boarding.dispatch_trip));
const status = computed(() => props.boarding?.status || "Pending");
const wrongBus = computed(() => props.boarding?.wrong_bus || null);
const correctTripLabel = computed(() => {
  const wb = wrongBus.value;
  if (!wb) return "";
  return wb.correct_trip || "";
});
const correctDriverPhone = computed(() => wrongBus.value?.correct_driver?.phone || "");

const driverArrived = computed(() => !!props.boarding?.driver_arrived?.arrived);

const boardingWindow = computed(() => props.boarding?.boarding_window || null);
const canConfirm = computed(() =>
  boardingWindow.value ? !!boardingWindow.value.can_confirm : true,
);

const waitCount = ref(props.boarding?.wait_count || 0);
const waitMax = computed(() => props.boarding?.wait_max || 0);
const waitCapReached = computed(() => waitMax.value > 0 && waitCount.value >= waitMax.value);
const canRequestWait = computed(
  () => hasTrip.value && !BOARDING_SETTLED.includes(status.value),
);

watch(
  () => props.boarding?.wait_count,
  (n) => {
    if (typeof n === "number") waitCount.value = n;
  },
);

const nowMs = ref(Date.now());
let clock = null;
function ensureClock() {
  if (clock) return;
  clock = setInterval(() => (nowMs.value = Date.now()), 1000);
}
onUnmounted(() => clock && clearInterval(clock));

function tsToMs(ts) {
  if (!ts) return null;
  const m = String(ts).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)).getTime();
}

const departSecs = computed(() => {
  const at = tsToMs(props.boarding?.notify_at);
  if (at === null) return null;
  const window = (props.boarding?.notify_window_seconds || 0) * 1000;
  ensureClock();
  const remaining = Math.ceil((at + window - nowMs.value) / 1000);
  return Math.max(0, remaining);
});

const waitCountdown = computed(() => {
  const at = tsToMs(props.boarding?.wait_at);
  if (at === null) return null;
  const window = (props.boarding?.wait_window_seconds || 0) * 1000;
  ensureClock();
  const remaining = Math.ceil((at + window - nowMs.value) / 1000);
  return remaining > 0 ? remaining : null;
});

const claimError = ref("");
const claim = createResource({
  url: "apex.salis.api.boarding_flow.worker_claim_boarded",
  onSuccess: () => {
    claimError.value = "";
    emitRefresh();
  },
  onError: (e) => {
    claimError.value = resourceErrorMessage(e, "transport.atPickupFailed");
  },
});
function doClaim() {
  claimError.value = "";
  claim.submit({ token: TOKEN });
}

const waitError = ref("");
const wait = createResource({
  url: "apex.salis.api.boarding_flow.worker_request_wait",
  onSuccess: (data) => {
    waitError.value = "";
    if (typeof data?.wait_count === "number") waitCount.value = data.wait_count;
    emitRefresh();
  },
  onError: (e) => {
    waitError.value = resourceErrorMessage(e, "transport.atPickupFailed");
  },
});
function doWait() {
  waitError.value = "";
  wait.submit({ token: TOKEN });
}

const emit = defineEmits(["refresh"]);
function emitRefresh() {
  emit("refresh");
}

const passOpen = ref(false);
const passErrorMsg = ref("");
const passResource = createResource({
  url: "apex.salis.api.masar.get_worker_boarding_pass",
  params: { token: TOKEN },
  onError: (e) => {
    passErrorMsg.value = resourceErrorMessage(e, "boarding.failed");
  },
  onSuccess: () => {
    passErrorMsg.value = "";
  },
});
const passData = computed(() => passResource.data?.pass || null);
const passLoading = computed(() => passResource.loading);
const passError = computed(() => passErrorMsg.value || passResource.error);
function openPass() {
  if (passData.value) {
    passOpen.value = true;
    return;
  }
  passResource.fetch().then(() => {
    if (passData.value) passOpen.value = true;
  });
}
</script>

<style scoped>
.bflow-panel {
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface);
}
.bflow-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.bflow-panel-title {
  font-size: var(--fs-h3);
  font-weight: 800;
}
.bflow-line {
  margin: 2px 0;
  font-size: var(--fs-sm);
}
.bflow-strong {
  font-weight: 800;
  color: var(--c-ink);
}
.bflow-muted {
  color: var(--c-muted);
}

.bflow-wrong {
  border-color: var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.bflow-wrong .bflow-strong,
.bflow-wrong .bflow-muted {
  color: inherit;
}

.bflow-departing {
  border-color: var(--c-warning);
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.bflow-countdown {
  font-size: var(--fs-h1);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.bflow-arrived {
  border-color: var(--c-success);
  background: var(--c-success-bg);
  color: var(--c-success);
}
.bflow-arrived .bflow-line {
  color: inherit;
}

.bflow-status {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-lg);
  border: var(--border-width) solid var(--c-border);
}
.bflow-status p {
  margin: 0;
  font-size: var(--fs-sm);
}
.bflow-ok {
  background: var(--c-success-bg);
  color: var(--c-success);
}
.bflow-ok .bflow-strong,
.bflow-ok .bflow-muted {
  color: inherit;
}
.bflow-danger {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.bflow-danger .bflow-strong,
.bflow-danger .bflow-muted {
  color: inherit;
}
.bflow-stale {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-lg);
  border: var(--border-width) solid var(--c-warning);
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.bflow-stale p {
  margin: 0;
  font-size: var(--fs-sm);
}
.bflow-stale .bflow-strong,
.bflow-stale .bflow-muted {
  color: inherit;
}
.bflow-wait-note {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--c-warning);
  margin: 0;
}
.bflow-wait-used {
  font-size: var(--fs-xs);
  color: var(--c-muted);
  text-align: center;
  margin: 0;
}
</style>
