<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="sheet-overlay" @click.self="close">
    <div ref="panel" class="sheet" role="dialog" aria-modal="true" :aria-label="t('manual.title')">
      <div class="sheet-bar">
        <span class="font-bold">{{ t("manual.title") }}</span>
        <button class="sheet-close" :aria-label="t('manual.close')" @click="close">
          <Icon name="x" :size="20" />
        </button>
      </div>

      <p class="sheet-hint">{{ t("manual.hint") }}</p>

      <Skeleton v-if="sheet.loading && !data" :rows="3" />
      <ErrorState v-else-if="sheet.error && !data" :message="t('errors.loadFailed')" @retry="sheet.reload()" />

      <template v-else-if="data">
        <ul v-if="data.workers && data.workers.length" class="sheet-list">
          <li v-for="w in data.workers" :key="w.employee" class="sheet-row">
            <label class="sheet-check">
              <input
                type="checkbox"
                :checked="w.boarded || selected.has(w.employee)"
                :disabled="w.boarded || busy"
                @change="toggle(w.employee)"
              />
              <span class="min-w-0">
                <span class="font-semibold block truncate"><bdi>{{ w.employee_name || w.employee }}</bdi></span>
                <span v-if="w.pickup_point" class="text-xs text-muted">{{ w.pickup_point }}</span>
              </span>
            </label>
            <span v-if="w.boarded" class="pill pill-success shrink-0">
              <Icon name="badge" :size="14" /> {{ t("manual.aboard") }}
            </span>
          </li>
        </ul>
        <EmptyState v-else :title="t('manual.empty')" />

        <div class="sheet-actions">
          <button
            class="btn btn-primary"
            :disabled="busy || !selected.size"
            @click="confirm"
          >
            <Icon name="user" :size="16" />
            {{ t("manual.board", { n: selected.size }) }}
          </button>
          <button class="btn btn-outline" :disabled="busy" @click="close">{{ t("manual.close") }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "./Icon.vue";
import Skeleton from "./Skeleton.vue";
import EmptyState from "./EmptyState.vue";
import ErrorState from "./ErrorState.vue";
import { useOverlay } from "@shared/useOverlay.js";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t } = useI18n();

const props = defineProps({
  trip: { type: String, required: true },
});
const emit = defineEmits(["close", "boarded"]);

const panel = ref(null);
const selected = ref(new Set());
const busy = ref(false);

const sheet = createResource({
  url: "apex.salis.api.driver_portal.manual_boarding_sheet",
  params: { dispatch_trip: props.trip },
  auto: true,
});
const data = computed(() => sheet.data || null);

const board = createResource({
  url: "apex.salis.api.driver_portal.manual_board_workers",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

function toggle(employee) {
  const next = new Set(selected.value);
  next.has(employee) ? next.delete(employee) : next.add(employee);
  selected.value = next;
}

async function confirm() {
  if (busy.value || !selected.value.size) return;
  busy.value = true;
  try {
    const res = await board.submit({
      dispatch_trip: props.trip,
      workers: JSON.stringify([...selected.value]),
    });
    const n = res?.boarded?.length || 0;
    pushToast(t("manual.boarded", { n }), "ok");
    selected.value = new Set();
    emit("boarded", res);
    sheet.reload();
  } finally {
    busy.value = false;
  }
}

function close() {
  emit("close");
}

useOverlay({ active: () => true, container: panel, close });
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
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  color: inherit;
}
.sheet-hint {
  font-size: 0.8125rem;
  color: var(--c-ink-soft);
  margin-bottom: 12px;
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
.sheet-check {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  cursor: pointer;
}
.sheet-check input {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  accent-color: var(--c-primary);
}
.sheet-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
.sheet-actions .btn {
  flex: 1;
}
</style>
