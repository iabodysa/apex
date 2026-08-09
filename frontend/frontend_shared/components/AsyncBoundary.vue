<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <slot v-if="state === 'ready'" />
  <div
    v-else
    class="async-boundary"
    :data-state="state"
    :role="['loading', 'empty'].includes(state) ? 'status' : undefined"
    :aria-live="['loading', 'empty'].includes(state) ? 'polite' : undefined"
  >
    <span v-if="state === 'loading'" class="async-boundary-pulse" aria-hidden="true"></span>
    <Alert
      v-else-if="state === 'error' || state === 'offline' || state === 'stale'"
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

defineProps({
  state: {
    type: String,
    default: "ready",
    validator: (value) => ["ready", "loading", "empty", "error", "offline", "stale"].includes(value),
  },
  title: { type: String, default: "" },
  message: { type: String, default: "" },
  retryLabel: { type: String, default: "" },
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
.async-boundary-pulse {
  inline-size: 2.25rem;
  aspect-ratio: 1;
  border: 3px solid color-mix(in srgb, var(--c-primary) 22%, transparent);
  border-block-start-color: var(--c-primary);
  border-radius: 50%;
  animation: async-turn 0.8s linear infinite;
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
@keyframes async-turn {
  to { transform: rotate(1turn); }
}
</style>
