<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="sk" role="status" :aria-label="label">
    <span class="sk-block sk-tabs"></span>

    <div class="sk-card">
      <div class="sk-head">
        <span class="sk-block sk-line sk-line-label"></span>
        <span class="sk-block sk-pill"></span>
      </div>
      <div class="sk-totals">
        <span v-for="i in 3" :key="i" class="sk-block sk-line sk-line-total"></span>
      </div>
    </div>

    <div class="sk-card">
      <span class="sk-block sk-line sk-line-label"></span>
      <div v-for="i in rows" :key="i" class="sk-row">
        <span class="sk-block sk-mark"></span>
        <span class="sk-lines">
          <span class="sk-block sk-line sk-line-title"></span>
          <span class="sk-block sk-line sk-line-meta"></span>
          <span class="sk-block sk-bar"></span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 4 },
  label: { type: String, required: true },
});
</script>

<style scoped>
.sk {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.sk-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface-2);
}
.sk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.sk-totals {
  display: flex;
  gap: var(--sp-6);
}
.sk-row {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  min-height: var(--tap-md);
}
.sk-lines {
  flex: 1;
  min-width: 0;
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
.sk-tabs {
  height: var(--tap-md);
  width: 60%;
  max-width: calc(var(--sp-8) * 8);
  border-radius: var(--radius-pill);
}
.sk-mark {
  height: var(--sp-8);
  width: var(--sp-8);
  flex-shrink: 0;
  border-radius: var(--radius-sm);
}
.sk-line {
  height: var(--sp-3);
}
.sk-line-label {
  width: 30%;
}
.sk-line-title {
  width: 72%;
}
.sk-line-meta {
  width: 44%;
}
.sk-line-total {
  width: var(--sp-8);
  height: var(--sp-5);
}
.sk-bar {
  height: var(--sp-2);
  width: 100%;
  border-radius: var(--radius-pill);
}
.sk-pill {
  height: var(--sp-5);
  width: calc(var(--sp-8) * 2);
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
