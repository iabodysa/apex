<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div v-if="title || subtitle || $slots.heading || $slots.actions" class="section-head">
    <slot name="heading">
      <h2 v-if="title">{{ title }}</h2>
    </slot>
    <p v-if="subtitle" class="section-sub page-shell-sub">{{ subtitle }}</p>
    <slot name="actions" />
  </div>

  <slot name="toolbar" />

  <AsyncBoundary
    :state="boundaryState"
    :title="stateTitle"
    :message="stateMessage"
    :retry-label="t('common.retry')"
    :loading-label="loadingLabel || t('common.loading')"
    :skeleton-rows="skeletonRows"
    @retry="$emit('retry')"
  >
    <template v-if="$slots.skeleton" #skeleton><slot name="skeleton" /></template>

    <EmptyState v-if="state === 'empty'" :title="emptyTitle" :hint="emptyHint">
      <template v-if="$slots['empty-icon']" #icon><slot name="empty-icon" /></template>
      <template v-if="$slots['empty-action']" #action><slot name="empty-action" /></template>
    </EmptyState>

    <template v-else>
      <slot />
      <div v-if="dock && $slots.dock" class="hz-dock"><slot name="dock" /></div>
    </template>
  </AsyncBoundary>
</template>

<script setup>
import { computed } from "vue";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  state: {
    type: String,
    default: "ready",
    validator: (value) => ["ready", "loading", "empty", "error"].includes(value),
  },
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  loadingLabel: { type: String, default: "" },
  skeletonRows: { type: Number, default: 5 },
  errorTitle: { type: String, default: "" },
  errorDetail: { type: String, default: "" },
  emptyTitle: { type: String, default: "" },
  emptyHint: { type: String, default: "" },
  dock: { type: Boolean, default: true },
});

defineEmits(["retry"]);

const { t } = useI18n();

const boundaryState = computed(() => (props.state === "empty" ? "ready" : props.state));
const stateTitle = computed(() => (props.state === "error" ? props.errorTitle : ""));
const stateMessage = computed(() => {
  if (props.state !== "error") return "";
  const detail = props.errorDetail;
  return detail && detail !== props.errorTitle ? detail : t("errors.retryHint");
});
</script>

<style scoped>
.page-shell-sub {
  flex-basis: 100%;
  order: 1;
}
</style>
