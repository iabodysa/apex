<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <button
    type="button"
    class="row"
    :class="{ 'row-open': open, 'row-edited': edited }"
    :aria-current="open ? 'true' : undefined"
    :aria-label="t('list.openItem', { name: row.item_name })"
    @click="$emit('open')"
  >
    <span class="row-mark"><Icon name="box" :size="20" /></span>

    <span class="row-id">
      <span class="row-name">{{ row.item_name }}</span>
      <span class="row-meta">
        <span>{{ tEnum("category", row.item_category) }}</span>
        <span class="row-sep" aria-hidden="true">·</span>
        <span>{{ t("card.counted") }} <bdi class="mono">{{ fmt(model.counted_quantity) }}</bdi></span>
        <span class="row-sep" aria-hidden="true">·</span>
        <span>{{ t("card.expected") }} <bdi class="mono">{{ fmt(row.expected_quantity) }}</bdi></span>
      </span>
    </span>

    <span class="row-end">
      <Badge v-if="edited" theme="blue" size="sm" :label="t('list.edited')" />
      <Badge :theme="varianceTheme" size="lg">
        <template #prefix><Icon :name="varianceIcon" :size="16" /></template>
        <bdi class="mono">{{ varianceText }}</bdi>
      </Badge>
    </span>
  </button>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, tEnum } = useI18n();

const props = defineProps({
  row: { type: Object, required: true },
  model: { type: Object, required: true },
  edited: { type: Boolean, default: false },
  open: { type: Boolean, default: false },
});

defineEmits(["open"]);

function fmt(v) {
  const n = Number(v || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");
}

const variance = computed(
  () => Number(props.model.counted_quantity || 0) - Number(props.row.expected_quantity || 0),
);
const varianceText = computed(() => (variance.value > 0 ? "+" + fmt(variance.value) : fmt(variance.value)));
const varianceTheme = computed(() => {
  if (variance.value < 0) return "red";
  if (variance.value > 0) return "orange";
  return "green";
});
const varianceIcon = computed(() => {
  if (variance.value < 0) return "triangle-alert";
  if (variance.value > 0) return "scale";
  return "check";
});
</script>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  min-height: var(--tap-lg);
  padding: var(--sp-3) var(--sp-4);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  background: var(--c-surface-2);
  text-align: start;
  cursor: pointer;
  touch-action: manipulation;
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}
@media (hover: hover) {
  .row:hover {
    border-color: var(--c-border-strong);
  }
}
.row:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 2px;
}
.row-edited {
  border-inline-start: 3px solid var(--c-primary);
}
.row-open {
  border-color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 7%, var(--c-surface-2));
}

.row-mark {
  display: grid;
  place-items: center;
  height: var(--tap-min);
  width: var(--tap-min);
  flex-shrink: 0;
  border-radius: var(--radius);
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}

.row-id {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.row-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.row-sep {
  color: var(--c-border-strong);
}

.row-end {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-shrink: 0;
}
</style>
