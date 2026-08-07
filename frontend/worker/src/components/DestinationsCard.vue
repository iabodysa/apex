<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Panel :title="t('home.more')">
    <nav class="dest-rows">
      <router-link v-for="dest in destinations" :key="dest.to" :to="dest.to" class="dest-row">
        <span class="dest-mark"><Icon :name="dest.icon" :size="20" /></span>
        <span class="dest-label">{{ t(dest.labelKey) }}</span>
        <Badge
          v-if="dest.count"
          class="tone-badge"
          theme="blue"
          variant="subtle"
          size="md"
          :label="String(dest.count)"
        />
        <Icon name="chevron" :size="16" class="dest-chevron rtl-flip" />
      </router-link>
    </nav>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps({
  openRequests: { type: Number, default: 0 },
});

const destinations = computed(() => [
  { to: "/accommodation", icon: "bed", labelKey: "nav.accommodation", count: 0 },
  { to: "/requests", icon: "doc", labelKey: "nav.requests", count: props.openRequests },
  { to: "/custody", icon: "briefcase", labelKey: "nav.custody", count: 0 },
  { to: "/profile", icon: "user", labelKey: "nav.profile", count: 0 },
]);
</script>

<style scoped>
.dest-rows {
  display: flex;
  flex-direction: column;
}
.dest-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: var(--tap-md);
  padding-block: var(--sp-2);
  border-top: var(--border-width) solid var(--c-border);
  color: var(--c-ink);
  text-decoration: none;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.dest-row:first-child {
  border-top: none;
}
@media (hover: hover) {
  .dest-row:hover {
    background: color-mix(in srgb, var(--c-ink) 6%, transparent);
  }
}
.dest-row:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: -3px;
  border-radius: var(--radius-sm);
}
.dest-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  height: var(--sp-8);
  width: var(--sp-8);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  color: var(--c-primary);
}
.dest-label {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
}
.dest-chevron {
  flex-shrink: 0;
  color: var(--c-muted);
}
</style>
