<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="sk" role="status" :aria-label="label">
    <div v-for="n in rows" :key="n" class="sk-row">
      <span class="sk-block sk-mark"></span>
      <span class="sk-lines">
        <span class="sk-block sk-line sk-line-wide"></span>
        <span class="sk-block sk-line sk-line-narrow"></span>
      </span>
      <span class="sk-block sk-pill"></span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 5 },
  label: { type: String, required: true },
});
</script>

<style scoped>
.sk {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.sk-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: 68px;
  padding: var(--sp-3) var(--sp-1);
  border-block-end: var(--border-width) solid var(--c-border);
  background: transparent;
}
.sk-lines {
  flex: 1;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.sk-block {
  display: block;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-ink) 9%, transparent);
  animation: sk-pulse 1.4s ease-in-out infinite;
}
.sk-mark {
  block-size: var(--sp-8);
  inline-size: var(--sp-8);
  flex-shrink: 0;
  border-radius: var(--radius);
}
.sk-line {
  block-size: var(--sp-3);
}
.sk-line-wide {
  inline-size: 68%;
}
.sk-line-narrow {
  inline-size: 38%;
}
.sk-pill {
  block-size: var(--sp-5);
  inline-size: var(--sp-8);
  flex-shrink: 0;
  border-radius: var(--radius-pill);
}

@keyframes sk-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk-block {
    animation: none;
  }
}
</style>
