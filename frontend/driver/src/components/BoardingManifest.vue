<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="sheet-overlay" @click.self="close">
    <div ref="sheet" class="sheet" role="dialog" aria-modal="true" :aria-label="t('manifest.title')">
      <div class="sheet-bar">
        <span class="font-bold">{{ t("manifest.title") }}</span>
        <Button
          class="sheet-close"
          variant="ghost"
          size="md"
          :label="t('manifest.close')"
          @click="close"
        >
          <template #icon><Icon name="x" :size="20" /></template>
        </Button>
      </div>

      <p class="sheet-hint">{{ t("manifest.hint") }}</p>

      <div v-if="!summary" class="flex flex-wrap items-center gap-2 mb-4">
        <Button
          class="flex-1"
          variant="solid"
          theme="green"
          size="xl"
          :label="t('trips.scanBoarding')"
          @click="emit('open-scan')"
        >
          <template #prefix><Icon name="qr" :size="16" /></template>
        </Button>
        <Button
          class="flex-1"
          variant="outline"
          size="xl"
          :label="t('trips.manualBoarding')"
          @click="emit('open-manual')"
        >
          <template #prefix><Icon name="user" :size="16" /></template>
        </Button>
      </div>

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
              <span v-if="w.wait_count" class="pill pill-warning shrink-0">
                <Icon name="alert" :size="12" /> {{ t("manifest.remaining", { n: w.wait_count }) }}
              </span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span class="pill shrink-0" :class="pillClass(w.status)">{{ te("boardingStatus", w.status) }}</span>
              <Button
                v-if="w.status === BOARDING.BOARDED"
                class="mini-btn mini-no"
                variant="ghost"
                theme="red"
                size="sm"
                :disabled="busy === w.employee"
                :label="t('manifest.notBoarded')"
                @click="markNotBoarded(w)"
              >
                <template #icon><Icon name="x" :size="14" /></template>
              </Button>
            </div>
          </li>
        </ul>
        <EmptyState v-else :title="t('manifest.empty')" />

        <div v-if="hasPending" class="notify-row">
          <Button
            class="notify-action"
            variant="outline"
            size="xl"
            :disabled="acting"
            :loading="notifyRes.loading"
            :label="graceElapsed ? t('manifest.notify') : t('manifest.notifySoft')"
            @click="notify"
          >
            <template #prefix><Icon name="alert" :size="16" /></template>
          </Button>
          <span v-if="graceElapsed" class="text-xs text-muted transition-colors duration-300" :style="reminderStyle">
            {{ t("manifest.notifyHint", { n: maxNotifySent, max: notifyMaxCount }) }}
          </span>
          <span v-else class="text-xs text-muted">{{ t("manifest.graceWaiting") }}</span>
        </div>

        <div class="sheet-actions">
          <Button
            class="flex-1"
            variant="solid"
            theme="green"
            size="xl"
            :disabled="acting"
            :loading="departRes.loading"
            :label="t('manifest.depart')"
            @click="depart"
          >
            <template #prefix><Icon name="route" :size="16" /></template>
          </Button>
          <Button
            class="flex-1"
            variant="outline"
            size="xl"
            :disabled="acting"
            :label="t('manifest.close')"
            @click="close"
          />
        </div>
        <p class="text-xs text-muted mt-2">{{ t("manifest.departHint") }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, createResource } from "frappe-ui";
import { BOARDING, BOARDING_REFUSED } from "@shared/statusVocabularies";
import Icon from "./Icon.vue";
import Skeleton from "./Skeleton.vue";
import EmptyState from "./EmptyState.vue";
import ErrorState from "./ErrorState.vue";
import { useI18n } from "../i18n";
import { useOverlay } from "@shared/useOverlay.js";
import { pushToast } from "../toast";
import { useDriverRealtime } from "../realtime.js";

const { t, te } = useI18n();

const props = defineProps({
  trip: { type: String, required: true },
});
const emit = defineEmits(["close", "finalized", "open-scan", "open-manual"]);

const panel = createResource({
  url: "apex.salis.api.boarding_flow.get_trip_boarding",
  params: { dispatch_trip: props.trip },
  auto: true,
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
const data = computed(() => panel.data || null);
const workers = computed(() => data.value?.workers || []);
const notifyMaxCount = computed(() => data.value?.notify_max_count || 0);
const graceElapsed = computed(() => !!data.value?.grace_elapsed);
const hasPending = computed(() => workers.value.some((w) => w.status === "Pending"));
const maxNotifySent = computed(() =>
  workers.value.reduce((m, w) => Math.max(m, w.notify_count || 0), 0),
);

const reminderStyle = computed(() => {
  if (maxNotifySent.value === 1) {
    return { color: "var(--c-success)", fontWeight: "700" };
  } else if (maxNotifySent.value === 2) {
    return { color: "var(--c-warning-ink)", fontWeight: "700" };
  } else if (maxNotifySent.value >= notifyMaxCount.value) {
    return { color: "var(--c-danger)", fontWeight: "700" };
  }
  return {};
});

const busy = ref(null);
const acting = ref(false);
const summary = ref(null);

function pillClass(status) {
  if (status === BOARDING.BOARDED) return "pill-success";
  if (BOARDING_REFUSED.includes(status)) return "pill-danger";
  if (status === BOARDING.WORKER_CLAIMED) return "pill-warning";
  return "pill-accent";
}

const notBoardedRes = createResource({
  url: "apex.salis.api.boarding_flow.driver_mark_not_boarded",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function markNotBoarded(w) {
  if (busy.value) return;
  busy.value = w.employee;
  try {
    await notBoardedRes.submit({ dispatch_trip: props.trip, employee: w.employee });
    pushToast(t("manifest.unmarked"), "ok");
    panel.reload();
  } finally {
    busy.value = null;
  }
}

const notifyRes = createResource({
  url: "apex.salis.api.boarding_flow.notify_remaining_passengers",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function notify() {
  if (acting.value) return;
  acting.value = true;
  try {
    const res = await notifyRes.submit({ dispatch_trip: props.trip });
    pushToast(res?.grace_elapsed ? t("manifest.notifyDone") : t("manifest.notifySoftDone"), "ok");
    panel.reload();
  } finally {
    acting.value = false;
  }
}

const departRes = createResource({
  url: "apex.salis.api.boarding_flow.depart_and_finalize",
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
    panel.reload();
  } finally {
    acting.value = false;
  }
}

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

useDriverRealtime(onBoarding);

const sheet = ref(null);

function close() {
  emit("close");
}

useOverlay({ active: () => true, container: sheet, close });
</script>

<style scoped>
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: var(--c-scrim);
}
.sheet {
  width: 100%;
  max-width: 520px;
  max-height: 86vh;
  overflow-y: auto;
  background: var(--c-surface);
  color: var(--c-ink);
  border-radius: var(--radius) var(--radius) 0 0;
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
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  color: inherit;
}
.sheet-hint {
  font-size: 0.8125rem;
  color: var(--c-ink-soft);
  margin-bottom: 12px;
}
.depart-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: var(--radius);
  font-size: 0.875rem;
  font-weight: 700;
  background: var(--c-success-bg);
  color: var(--c-success);
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
  border-radius: var(--radius-sm);
}
.sheet-row + .sheet-row {
  border-top: 1px solid var(--c-border);
}
.mini-btn {
  position: relative;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.mini-btn::after {
  content: "";
  position: absolute;
  inset: calc((var(--tap-min) - 30px) / -2);
}
.mini-no {
  background: var(--c-surface-2);
  color: var(--c-ink);
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
.notify-action {
  width: auto;
}
.sheet-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
</style>
