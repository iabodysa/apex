<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <slot v-if="state === 'ready'" />
  <div v-else-if="state === 'loading'" class="async-boundary-skeleton">
    <slot name="skeleton">
      <ListSkeleton :rows="skeletonRows" :label="title || loadingLabel" />
    </slot>
  </div>
  <div
    v-else
    class="async-boundary"
    :data-state="state"
    :role="['loading', 'empty'].includes(state) ? 'status' : undefined"
    :aria-live="['loading', 'empty'].includes(state) ? 'polite' : undefined"
  >
    <Alert
      v-if="state === 'error' || state === 'offline' || state === 'stale'"
      :theme="state === 'error' ? 'red' : 'yellow'"
      :title="title"
      :description="message"
      :dismissable="false"
    />
    <div v-else class="async-boundary-copy">
      <h2 v-if="title">{{ title }}</h2>
      <p v-if="message">{{ message }}</p>
    </div>
    <Button
      v-if="retryLabel && ['error', 'offline', 'stale'].includes(state)"
      class="async-boundary-retry"
      variant="outline"
      size="xl"
      :label="retryLabel"
      @click="$emit('retry')"
    />
    <slot name="state" />
  </div>
</template>

<script setup>
import { Alert, Button } from "frappe-ui";
import ListSkeleton from "./ListSkeleton.vue";

defineProps({
  state: {
    type: String,
    default: "ready",
    validator: (value) => ["ready", "loading", "empty", "error", "offline", "stale"].includes(value),
  },
  title: { type: String, default: "" },
  message: { type: String, default: "" },
  retryLabel: { type: String, default: "" },
  skeletonRows: { type: Number, default: 4 },
  loadingLabel: { type: String, default: "Loading" },
});

defineEmits(["retry"]);
</script>

<style scoped>
.async-boundary {
  min-block-size: 12rem;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: var(--sp-3);
  padding: clamp(var(--sp-5), 6vw, var(--sp-8));
  border-block: 1px solid var(--c-border);
  color: var(--c-ink-soft);
  text-align: center;
}
.async-boundary-skeleton {
  display: block;
}
.async-boundary-copy h2,
.async-boundary-copy p {
  margin: 0;
}
.async-boundary-copy h2 {
  color: var(--c-ink);
  font-size: var(--fs-h2);
}
.async-boundary-copy p {
  margin-block-start: var(--sp-2);
  font-family: var(--font-serif);
  line-height: 1.65;
}
.async-boundary-retry {
  min-block-size: var(--tap-min);
}
</style>
