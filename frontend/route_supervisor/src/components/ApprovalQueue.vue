<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <section class="queue">
    <header class="queue-head">
      <div>
        <h2>{{ t("queue.title") }}</h2>
        <p>{{ t("queue.subtitle", { n: pending.length }) }}</p>
      </div>
    </header>

    <EmptyState v-if="!pending.length" :title="t('queue.empty')" :hint="t('queue.emptyHint')">
      <template #icon><Icon name="circle-check" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <ul v-else class="queue-list">
      <li v-for="plan in pending" :key="plan.name" class="queue-row">
        <button type="button" class="queue-open" @click="$emit('open', plan.name)">
          <span class="qr-name">{{ plan.route_name || plan.name }}</span>
          <span class="qr-meta">
            <span v-if="plan.project"><Icon name="badge" :size="12" /> {{ plan.project }}</span>
            <span v-if="plan.shift"><Icon name="clock" :size="12" /> {{ t("shift." + plan.shift) }}</span>
            <span><Icon name="pin" :size="12" /> {{ t("list.stops", { n: plan.total_stops }) }}</span>
            <span v-if="plan.driver"><Icon name="user" :size="12" /> {{ plan.driver }}</span>
            <span v-if="plan.vehicle"><Icon name="truck" :size="12" /> {{ plan.vehicle }}</span>
          </span>
        </button>
        <div class="qr-actions">
          <button class="primary-btn" :disabled="busy" @click="$emit('approve', plan.name)">
            <Icon name="check" :size="16" /> {{ t("approval.approve") }}
          </button>
          <button class="danger-btn" :disabled="busy" @click="$emit('reject', plan.name)">
            <Icon name="x" :size="16" /> {{ t("approval.reject") }}
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed } from "vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../Icon.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  plans: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});
defineEmits(["open", "approve", "reject"]);

const { t } = useI18n();
const pending = computed(() => props.plans.filter((plan) => plan.approval === "Pending"));
</script>

<style scoped>
.queue {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.queue-head h2 {
  margin: 0;
  font-size: 17px;
}
.queue-head p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--c-muted);
}
.queue-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.queue-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  background: var(--c-surface);
}
.queue-open {
  flex: 1 1 260px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 0;
  background: none;
  text-align: start;
  cursor: pointer;
  color: inherit;
  padding: 0;
}
.qr-name {
  font-weight: 600;
  transition: color 0.15s;
}
/* Gated so a touch tap never leaves a sticky hover behind. */
@media (hover: hover) {
  .queue-open:hover .qr-name {
    color: var(--c-primary);
    text-decoration: underline;
  }
}
.qr-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--c-muted);
}
.qr-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.qr-actions {
  display: flex;
  gap: 8px;
}
</style>
