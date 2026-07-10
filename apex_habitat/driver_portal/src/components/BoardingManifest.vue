<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <!-- Boarding manifest panel for a STARTED trip. Lists each Trip Boarding State
       worker with a status pill. A worker's "I'm on the bus" claim self-confirms
       (no per-worker driver approval); the driver intervenes only for an exception
       — a "Not boarded" override on a Boarded row (driver_mark_not_boarded) reverses
       a mistaken/wrong-bus self-confirm. "Notify remaining" nudges the still-Pending
       workers (notify_remaining_passengers); before grace it's a soft ping, so
       the label reflects that. "Depart & finalize" closes the manifest
       (depart_and_finalize) and shows the boarded/absent/pending summary. Boarding
       realtime (boarding_update / wait_request / boarding_confirmed / boarding_unmarked)
       refetches so a worker's self-confirm or wait surfaces live; socket errors are
       swallowed in realtime.js so the manual fetch always carries the manifest. -->
  <div class="sheet-overlay" role="dialog" aria-modal="true" @click.self="close">
    <div class="sheet">
      <div class="sheet-bar">
        <span class="font-bold">{{ t("manifest.title") }}</span>
        <button class="sheet-close" :aria-label="t('manifest.close')" @click="close">
          <Icon name="x" :size="20" />
        </button>
      </div>

      <p class="sheet-hint">{{ t("manifest.hint") }}</p>

      <!-- Inline Boarding Actions -->
      <div v-if="!summary" class="flex flex-wrap items-center gap-2 mb-4">
        <button class="btn btn-accent flex-1" @click="emit('open-scan')">
          <Icon name="qr" :size="16" /> {{ t("trips.scanBoarding", "Scan Boarding") }}
        </button>
        <button class="btn btn-outline flex-1" @click="emit('open-manual')">
          <Icon name="user" :size="16" /> {{ t("trips.manualBoarding", "Manual Boarding") }}
        </button>
      </div>

      <!-- Departure summary replaces the list once finalized. -->
      <div v-if="summary" class="depart-summary">
        <Icon name="badge" :size="16" class="shrink-0" />
        <span>{{ t("manifest.departSummary", summary) }}</span>
      </div>

      <Skeleton v-if="panel.loading && !data" :rows="3" />
      <ErrorState v-else-if="panel.error && !data" :message="t('errors.loadFailed')" @retry="panel.reload()" />

      <template v-else-if="data">
        <ul v-if="workers.length" class="sheet-list">
          <li v-for="w in workers" :key="w.employee" class="sheet-row">
            <div class="min-w-0 flex items-center gap-2">
              <Icon name="user" :size="14" class="text-primary shrink-0" />
              <span class="font-semibold truncate"><bdi>{{ w.employee }}</bdi></span>
              <!-- A worker asking to wait shows a small badge with the count. -->
              <span v-if="w.wait_count" class="pill pill-warning shrink-0">
                <Icon name="alert" :size="12" /> {{ t("manifest.remaining", { n: w.wait_count }) }}
              </span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span class="pill shrink-0" :class="pillClass(w.status)">{{ te("boardingStatus", w.status) }}</span>
              <!-- Exception override: a worker self-confirmed but isn't really aboard. -->
              <button
                v-if="w.status === 'Boarded'"
                class="mini-btn mini-no"
                :disabled="busy === w.employee"
                :aria-label="t('manifest.notBoarded')"
                @click="markNotBoarded(w)"
              >
                <Icon name="x" :size="14" />
              </button>
            </div>
          </li>
        </ul>
        <EmptyState v-else :title="t('manifest.empty')" />

        <!-- Notify reflects whether grace has elapsed: a soft ping before, a
             counted reminder after (n of max). -->
        <div v-if="hasPending" class="notify-row">
          <button class="btn btn-outline" :disabled="acting" @click="notify">
            <Icon name="alert" :size="16" />
            {{ graceElapsed ? t("manifest.notify") : t("manifest.notifySoft") }}
          </button>
          <span v-if="graceElapsed" class="text-xs text-muted transition-all duration-300" :style="reminderStyle">
            {{ t("manifest.notifyHint", { n: maxNotifySent, max: notifyMaxCount }) }}
          </span>
          <span v-else class="text-xs text-muted">{{ t("manifest.graceWaiting") }}</span>
        </div>

        <div class="sheet-actions">
          <button class="btn btn-dark" :disabled="acting" @click="depart">
            <Icon name="route" :size="16" /> {{ t("manifest.depart") }}
          </button>
          <button class="btn btn-outline" :disabled="acting" @click="close">{{ t("manifest.close") }}</button>
        </div>
        <p class="text-xs text-muted mt-2">{{ t("manifest.departHint") }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "./Icon.vue";
import Skeleton from "./Skeleton.vue";
import EmptyState from "./EmptyState.vue";
import ErrorState from "./ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import { connectDriverRealtime } from "../realtime.js";

const { t, te } = useI18n();

const props = defineProps({
  // The started Dispatch Trip whose boarding manifest is managed.
  trip: { type: String, required: true },
});
// `finalized` after a successful depart so the parent can refresh its trip card.
const emit = defineEmits(["close", "finalized", "open-scan", "open-manual"]);

// Read on open / after every action via the pure-read get_trip_boarding (same
// shape, no side effects) — viewing the manifest must never bump a worker's
// notify_count. The explicit "Notify remaining" button is the only path that
// calls the write endpoint notify_remaining_passengers (see notify() below).
const panel = createResource({
  url: "apex_habitat.salis.api.boarding_flow.get_trip_boarding",
  params: { dispatch_trip: props.trip },
  auto: true,
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
const data = computed(() => panel.data || null);
const workers = computed(() => data.value?.workers || []);
const notifyMaxCount = computed(() => data.value?.notify_max_count || 0);
const graceElapsed = computed(() => !!data.value?.grace_elapsed);
const hasPending = computed(() => workers.value.some((w) => w.status === "Pending"));
// The highest notify_count among pending workers = how many counted reminders
// have gone out this trip (they're nudged together, so they share the count).
const maxNotifySent = computed(() =>
  workers.value.reduce((m, w) => Math.max(m, w.notify_count || 0), 0),
);

const reminderStyle = computed(() => {
  if (maxNotifySent.value === 1) {
    return { color: "var(--c-success)", fontWeight: "600" };
  } else if (maxNotifySent.value === 2) {
    return { color: "var(--c-warning)", fontWeight: "600" };
  } else if (maxNotifySent.value >= notifyMaxCount.value) {
    return { color: "var(--c-danger)", fontWeight: "700" };
  }
  return {};
});

// `busy` holds the in-flight employee (per-row confirm/reject disable);
// `acting` guards the panel-level actions (notify / depart) against double taps.
const busy = ref(null);
const acting = ref(false);
const summary = ref(null);

function pillClass(status) {
  if (status === "Boarded") return "pill-success";
  if (status === "Absent" || status === "Driver Rejected") return "pill-danger";
  if (status === "Worker Claimed") return "pill-warning";
  return "pill-accent";
}

// Exception override only: reverse a worker's self-confirm (wrong bus / mistaken
// tap). There is no per-worker approval — a claim self-confirms server-side.
const notBoardedRes = createResource({
  url: "apex_habitat.salis.api.boarding_flow.driver_mark_not_boarded",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function markNotBoarded(w) {
  if (busy.value) return;
  busy.value = w.employee;
  try {
    await notBoardedRes.submit({ dispatch_trip: props.trip, employee: w.employee });
    pushToast(t("manifest.unmarked"), "ok");
    panel.reload(); // re-read the authoritative per-worker state
  } finally {
    busy.value = null;
  }
}

const notifyRes = createResource({
  url: "apex_habitat.salis.api.boarding_flow.notify_remaining_passengers",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function notify() {
  if (acting.value) return;
  acting.value = true;
  try {
    // The explicit nudge: the only write to notify_count. Re-read after so the
    // panel repaints the updated counts (notify returns the fresh state itself).
    const res = await notifyRes.submit({ dispatch_trip: props.trip });
    pushToast(res?.grace_elapsed ? t("manifest.notifyDone") : t("manifest.notifySoftDone"), "ok");
    panel.reload();
  } finally {
    acting.value = false;
  }
}

const departRes = createResource({
  url: "apex_habitat.salis.api.boarding_flow.depart_and_finalize",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function depart() {
  if (acting.value) return;
  acting.value = true;
  try {
    const res = await departRes.submit({ dispatch_trip: props.trip });
    summary.value = {
      boarded: res?.boarded || 0,
      absent: res?.absent || 0,
      pending: res?.pending || 0,
    };
    emit("finalized", res);
    panel.reload(); // repaint the final statuses behind the summary
  } finally {
    acting.value = false;
  }
}

// ── Realtime (boarding events on the Dispatch Trip room) ──
// A worker's wait/self-confirm or any boarding state change for THIS trip refetches
// the manifest so the pills repaint without a tap. wait_request / boarding_confirmed
// also toast so the driver notices an off-screen ask or a worker boarding.
let stopRealtime = () => {};
function onBoarding(event, payload) {
  if (payload.dispatch_trip && payload.dispatch_trip !== props.trip) return;
  if (event === "wait_request") {
    pushToast(
      t("manifest.waitRequest", {
        name: payload.employee || "",
        n: payload.wait_count || 0,
        max: data.value?.worker_wait_request_max || payload.wait_count || 0,
      }),
      "ok",
    );
  } else if (event === "boarding_confirmed") {
    pushToast(t("manifest.workerAboard", { name: payload.employee || "" }), "ok");
  }
  panel.reload();
}
onMounted(() => {
  // Pass a no-op trip handler (the manifest doesn't drive the trips list) plus the
  // boarding handler; realtime.js swallows every socket failure.
  stopRealtime = connectDriverRealtime(() => {}, onBoarding);
});
onUnmounted(() => {
  stopRealtime();
});

function close() {
  emit("close");
}
</script>

<style scoped>
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}
.sheet {
  width: 100%;
  max-width: 520px;
  max-height: 86vh;
  overflow-y: auto;
  background: var(--c-surface, #fff);
  color: var(--c-ink, #111);
  border-radius: 18px 18px 0 0;
  padding: 16px 16px calc(16px + env(safe-area-inset-bottom));
}
.sheet-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.sheet-close {
  font-size: 20px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: var(--radius-pill, 999px);
  background: var(--c-surface-2, #f1f1f1);
  color: inherit;
}
.sheet-hint {
  font-size: 0.8125rem;
  color: var(--c-ink-soft, #555);
  margin-bottom: 12px;
}
.depart-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.875rem;
  font-weight: 600;
  background: var(--c-success-bg, #dcfce7);
  color: var(--c-success, var(--brand-green));
}
.sheet-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sheet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 8px;
  border-radius: var(--radius-sm, 10px);
}
.sheet-row + .sheet-row {
  border-top: 1px solid var(--c-border, rgba(0, 0, 0, 0.06));
}
.mini-btn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm, 8px);
  flex-shrink: 0;
}
.mini-ok {
  background: var(--c-success, var(--brand-green));
  color: #fff;
}
.mini-no {
  background: var(--c-surface-2, #f1f1f1);
  color: var(--c-ink, #111);
}
.mini-btn:disabled {
  opacity: 0.6;
}
.notify-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}
.notify-row .btn {
  width: auto;
  padding-inline: 16px;
}
.sheet-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
.sheet-actions .btn {
  flex: 1;
}
</style>
