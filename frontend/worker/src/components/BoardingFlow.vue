<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- The live boarding flow for the soonest upcoming trip. Renders off the server's
     worker_trip_boarding(token) snapshot (fast-polled while a boarding window is
     active) and drives the three write endpoints: claim "on the bus", request a
     wait, and re-claim after a driver rejection. Also surfaces a departing
     countdown and the wrong-bus correction. Boarding-pass button lives here too,
     opening the full-screen overlay. All copy translatable, RTL-safe, themed. -->
<template>
  <div class="bflow space-y-3">
    <!-- WRONG BUS: scanned a vehicle that isn't this worker's trip. Full-width,
         unmissable; the only thing shown when set (it overrides the normal flow). -->
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
      <!-- STALE: the poll is failing, so everything below is drawn from an old
           snapshot. Say so, and keep the boarding writes disabled until it refreshes. -->
      <div v-if="stale" class="bflow-stale" role="status">
        <Icon name="alert" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.stale") }}</p>
          <p class="bflow-muted">{{ t("boarding.staleHint") }}</p>
        </div>
      </div>

      <!-- DRIVER ARRIVED: the driver marked arrival at this worker's pickup stop.
           A green, reassuring band shown while the worker is still boarding. -->
      <div v-if="driverArrived && !['Boarded', 'Absent'].includes(status)" class="bflow-panel bflow-arrived">
        <div class="bflow-panel-head">
          <Icon name="bus" :size="20" class="shrink-0 rtl-flip" />
          <span class="bflow-panel-title">{{ t("boarding.arrivedTitle") }}</span>
        </div>
        <p class="bflow-line">{{ t("boarding.arrivedHint") }}</p>
      </div>

      <!-- DEPARTING countdown: driver pressed depart; the vehicle leaves at
           notify_at + notify_window_seconds. Recomputed from the server stamp. -->
      <div v-if="departSecs !== null" class="bflow-panel bflow-departing">
        <div class="bflow-panel-head">
          <Icon name="bus" :size="20" class="shrink-0 rtl-flip" />
          <span class="bflow-panel-title">{{ t("boarding.departing") }}</span>
        </div>
        <p class="bflow-countdown">
          {{ departSecs > 0 ? t("boarding.departingIn", { s: departSecs }) : t("boarding.departingNow") }}
        </p>
      </div>

      <!-- STATUS-DRIVEN body. -->
      <!-- Boarded / Absent: terminal states, no actions. -->
      <div v-if="status === 'Boarded'" class="bflow-status bflow-ok">
        <Icon name="check" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.boardedTitle") }}</p>
          <p class="bflow-muted">{{ t("boarding.boardedHint") }}</p>
        </div>
      </div>
      <div v-else-if="status === 'Absent'" class="bflow-status bflow-danger">
        <Icon name="alert" :size="18" class="shrink-0" />
        <div>
          <p class="bflow-strong">{{ t("boarding.absentTitle") }}</p>
          <p class="bflow-muted">{{ t("boarding.absentHint") }}</p>
        </div>
      </div>

      <!-- Pending (default): the primary "I'm on the bus" action — it self-confirms
           (no driver approval); the worker goes straight to Boarded. If the driver
           later marks them not-boarded (an exception), the state resets to Pending
           and this button simply returns. -->
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

      <!-- WAIT request: available while still boarding (not boarded/absent). The
           cap + per-request countdown come from the server. -->
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

      <!-- Boarding pass: opens the full-screen overlay. -->
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
import { createResource } from "frappe-ui";
import Icon from "./Icon.vue";
import BoardingPassOverlay from "./BoardingPassOverlay.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { TOKEN } from "../utils/token";
import { waLink } from "../utils/phone";

const { t } = useI18n();

const props = defineProps({
  // The soonest upcoming trip (for the boarding-pass ticket fields).
  trip: { type: Object, default: null },
  // The live worker_trip_boarding snapshot (server state machine), polled by the
  // parent. Null/{trip:null} means no active boarding — the flow renders nothing.
  boarding: { type: Object, default: null },
  // True while the last poll FAILED, so this snapshot is known out of date. The
  // writes are blocked meanwhile: claiming "I'm on the bus" off a stale snapshot
  // can confirm a worker onto a trip the server has already moved on from.
  stale: { type: Boolean, default: false },
});

// --- Derived server state -------------------------------------------------
const hasTrip = computed(() => !!(props.boarding && props.boarding.dispatch_trip));
const status = computed(() => props.boarding?.status || "Pending");
const wrongBus = computed(() => props.boarding?.wrong_bus || null);
const correctTripLabel = computed(() => {
  const wb = wrongBus.value;
  if (!wb) return "";
  return wb.correct_trip || "";
});
const correctDriverPhone = computed(() => wrongBus.value?.correct_driver?.phone || "");

// P-046: "your driver has arrived at your pickup" — set by the poll once the driver
// marks arrival at this worker's own pickup stop. Null until then.
const driverArrived = computed(() => !!props.boarding?.driver_arrived?.arrived);

// Wait request: cap + counts. The flow allows it while the worker is still in a
// boarding window (a trip exists and it isn't a terminal state).
const waitCount = ref(props.boarding?.wait_count || 0);
const waitMax = computed(() => props.boarding?.wait_max || 0);
const waitCapReached = computed(() => waitMax.value > 0 && waitCount.value >= waitMax.value);
const canRequestWait = computed(
  () => hasTrip.value && !["Boarded", "Absent"].includes(status.value),
);

// Keep the local wait counter in sync when the polled snapshot advances.
watch(
  () => props.boarding?.wait_count,
  (n) => {
    if (typeof n === "number") waitCount.value = n;
  },
);

// --- Departing countdown (client tick from a server timestamp) ------------
// notify_at + notify_window_seconds is the absolute departure instant; we tick a
// local clock and recompute the remaining seconds so it survives re-renders/polls
// without drifting (the server stamp is the source of truth).
const nowMs = ref(Date.now());
let clock = null;
function ensureClock() {
  if (clock) return;
  clock = setInterval(() => (nowMs.value = Date.now()), 1000);
}
onUnmounted(() => clock && clearInterval(clock));

// Parse a backend "YYYY-MM-DD HH:MM:SS" (local) timestamp to epoch ms.
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

// Per-request wait countdown: wait_at + wait_window_seconds.
const waitCountdown = computed(() => {
  const at = tsToMs(props.boarding?.wait_at);
  if (at === null) return null;
  const window = (props.boarding?.wait_window_seconds || 0) * 1000;
  ensureClock();
  const remaining = Math.ceil((at + window - nowMs.value) / 1000);
  return remaining > 0 ? remaining : null;
});

// --- Write endpoints ------------------------------------------------------
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

// Ask the parent to re-poll the boarding snapshot right after a write so the UI
// reflects the new server state without waiting for the next interval tick.
const emit = defineEmits(["refresh"]);
function emitRefresh() {
  emit("refresh");
}

// --- Boarding pass (full-screen overlay) ----------------------------------
const passOpen = ref(false);
const passErrorMsg = ref("");
const passResource = createResource({
  url: "apex.salis.api.masar.get_worker_boarding_pass",
  params: { token: TOKEN },
  onError: (e) => {
    // Surface the failure (matches the claim/wait resources) instead of letting
    // it fall through to the static "none" text with no signal that a fetch failed.
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
  // Fetch once, then reveal the overlay as soon as the pass is available.
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

/* Wrong bus: a red, unmissable correction. */
.bflow-wrong {
  border-color: var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.bflow-wrong .bflow-strong,
.bflow-wrong .bflow-muted {
  color: inherit;
}

/* Departing: amber urgency band with a large countdown. */
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

/* Driver arrived: a calm green band reassuring the worker to head out. */
.bflow-arrived {
  border-color: var(--c-success);
  background: var(--c-success-bg);
  color: var(--c-success);
}
.bflow-arrived .bflow-line {
  color: inherit;
}

/* Inline status rows. */
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
/* Stale: an amber warning row, same shape as the inline status rows. */
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
