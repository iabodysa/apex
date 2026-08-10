<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <span class="status-label" :data-tone="safeTone">
    <span class="status-label-mark" aria-hidden="true"></span>
    <span>{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  label: { type: String, required: true },
  tone: { type: String, default: "neutral" },
});

const tones = new Set(["neutral", "accent", "info", "success", "warning", "danger"]);
const safeTone = computed(() => (tones.has(props.tone) ? props.tone : "neutral"));
</script>

<style scoped>
.status-label {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-block-size: 28px;
  max-inline-size: 100%;
  padding-inline: 0.65rem;
  border: 1px solid var(--status-border, var(--c-border-strong));
  border-radius: var(--radius-pill);
  background: var(--status-bg, transparent);
  color: var(--status-ink, var(--c-ink-soft));
  font-family: var(--font-brand);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  line-height: 1.2;
}
.status-label-mark {
  inline-size: 0.42rem;
  block-size: 0.42rem;
  flex: 0 0 auto;
  border-radius: 50%;
  background: currentColor;
}
.status-label[data-tone="accent"] {
  --status-bg: color-mix(in srgb, var(--c-mint) 20%, transparent);
  --status-border: color-mix(in srgb, var(--c-primary) 28%, transparent);
  --status-ink: var(--c-accent-ink);
}
.status-label[data-tone="info"] {
  --status-bg: var(--c-info-bg);
  --status-border: color-mix(in srgb, var(--c-info) 35%, transparent);
  --status-ink: var(--c-info);
}
.status-label[data-tone="success"] {
  --status-bg: var(--c-success-bg);
  --status-border: color-mix(in srgb, var(--c-success) 35%, transparent);
  --status-ink: var(--c-success);
}
.status-label[data-tone="warning"] {
  --status-bg: var(--c-warning-bg);
  --status-border: color-mix(in srgb, var(--c-warning) 35%, transparent);
  --status-ink: var(--c-warning);
}
.status-label[data-tone="danger"] {
  --status-bg: var(--c-danger-bg);
  --status-border: color-mix(in srgb, var(--c-danger) 35%, transparent);
  --status-ink: var(--c-danger);
}
</style>
