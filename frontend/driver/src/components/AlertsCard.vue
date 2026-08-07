<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Panel :title="t('home.needsAttention')">
    <template #status>
      <Badge class="tone-badge" theme="orange" variant="subtle" size="lg" :label="n(alerts.length)" />
    </template>

    <ul class="alert-rows">
      <li v-for="alert in alerts" :key="alert.key" class="alert-row">
        <span class="alert-mark" :class="'mark-' + alert.tone">
          <Icon :name="alert.icon" :size="20" />
        </span>
        <span class="alert-text">{{ alert.label }}</span>
        <Badge
          class="tone-badge"
          :theme="alert.tone === 'danger' ? 'red' : 'orange'"
          variant="subtle"
          size="md"
          :label="alert.badge"
        />
      </li>
    </ul>
  </Panel>
</template>

<script setup>
import { Badge } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, n } = useI18n();

defineProps({
  alerts: { type: Array, required: true },
});
</script>

<style scoped>
.alert-rows {
  display: flex;
  flex-direction: column;
}
.alert-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: var(--tap-md);
  padding-block: var(--sp-2);
  border-top: var(--border-width) solid var(--c-border);
}
.alert-row:first-child {
  border-top: none;
  padding-top: 0;
}
.alert-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  height: var(--sp-8);
  width: var(--sp-8);
  border-radius: var(--radius-sm);
}
.mark-warning {
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.mark-danger {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.alert-text {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
}
</style>
