<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div v-if="state && state !== 'at_stop'" class="bwin" :class="'bwin-' + state">
    <div class="bwin-head">
      <Icon :name="icon" :size="20" class="shrink-0 rtl-flip" />
      <span class="bwin-title">{{ title }}</span>
    </div>
    <p v-if="etaLine" class="bwin-eta">{{ etaLine }}</p>
    <p class="bwin-hint">{{ hint }}</p>
    <router-link
      v-if="state === 'departed'"
      to="/request-transport"
      class="btn btn-outline"
      style="text-decoration: none"
    >
      <Icon name="route" :size="18" class="rtl-flip" /> {{ t("boarding.missedRide") }}
    </router-link>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps({
  window: { type: Object, default: null },
});

const state = computed(() => props.window?.state || null);

const ICONS = {
  scheduled: "clock",
  en_route: "bus",
  departed: "alert",
  finished: "check",
};

const TITLES = {
  scheduled: "boarding.scheduledTitle",
  en_route: "home.enRoute",
  departed: "boarding.departedTitle",
  finished: "boarding.finishedTitle",
};

const HINTS = {
  scheduled: "boarding.scheduledHint",
  en_route: "boarding.enRouteHint",
  departed: "boarding.departedHint",
  finished: "boarding.finishedHint",
};

const icon = computed(() => ICONS[state.value] || "clock");
const title = computed(() => t(TITLES[state.value] || "boarding.scheduledTitle"));
const hint = computed(() => t(HINTS[state.value] || "boarding.scheduledHint"));

const etaLine = computed(() => {
  const eta = props.window?.eta_minutes;
  if (state.value !== "en_route" || typeof eta !== "number") return "";
  return t("home.etaArriving", { eta });
});
</script>

<style scoped>
.bwin {
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bwin-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bwin-title {
  font-size: var(--fs-h3);
  font-weight: 800;
}
.bwin-eta {
  font-size: var(--fs-h3);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  margin: 0;
}
.bwin-hint {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.bwin-en_route {
  border-color: var(--c-primary);
  color: var(--c-primary);
}
.bwin-departed {
  border-color: var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.bwin-departed .bwin-hint,
.bwin-en_route .bwin-hint {
  color: inherit;
}
.bwin-finished {
  border-color: var(--c-success);
  color: var(--c-success);
}
.bwin-finished .bwin-hint {
  color: inherit;
}
</style>
