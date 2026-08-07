<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <button
    type="button"
    class="row"
    :class="{ 'row-open': open }"
    :aria-current="open ? 'true' : undefined"
    :aria-label="t('delivery.openDelivery', { name: title })"
    @click="$emit('open')"
  >
    <span class="row-mark" :class="released ? 'row-mark-ready' : ''">
      <Icon :name="released ? 'key' : 'truck'" :size="20" />
    </span>

    <span class="row-id">
      <bdi class="row-name mono">{{ title }}</bdi>
      <span class="row-meta">
        <span>{{ delivery.from_building || t("common.none") }}</span>
        <Icon class="row-arrow" name="chevron" :size="16" />
        <span>{{ delivery.to_building || t("common.none") }}</span>
      </span>
      <span class="track" :aria-label="t('delivery.exitStep', { n: cleared })">
        <span v-for="g in 3" :key="g" class="track-bar" :class="g <= cleared ? 'track-bar-on' : ''"></span>
      </span>
    </span>

    <Badge :theme="released ? 'green' : 'orange'" size="lg" :label="statusLabel" />
  </button>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { clearedCount } from "../gates";

const { t } = useI18n();

const props = defineProps({
  delivery: { type: Object, required: true },
  open: { type: Boolean, default: false },
});

defineEmits(["open"]);

const title = computed(() => props.delivery.asset_serial_number || props.delivery.name);
const released = computed(() => props.delivery.status === "Released");
const cleared = computed(() => clearedCount(props.delivery));
const statusLabel = computed(() =>
  released.value ? t("delivery.readyToReceive") : t("delivery.awaitingExits"),
);
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
  color: var(--c-warning);
  background: var(--c-warning-bg);
}
.row-mark-ready {
  color: var(--c-success);
  background: var(--c-success-bg);
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
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--c-muted);
  min-width: 0;
}
.row-meta > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-arrow {
  flex-shrink: 0;
}

.track {
  display: flex;
  gap: var(--sp-1);
  margin-top: var(--sp-1);
}
.track-bar {
  height: var(--sp-1);
  width: var(--sp-6);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 14%, transparent);
}
.track-bar-on {
  background: var(--c-success);
}
</style>
