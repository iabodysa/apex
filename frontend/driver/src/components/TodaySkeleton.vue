<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="sk" role="status" :aria-label="label">
    <div class="sk-card">
      <div class="sk-head">
        <span class="sk-block sk-line sk-line-label"></span>
        <span class="sk-block sk-pill"></span>
      </div>
      <span class="sk-block sk-line sk-line-value"></span>
    </div>

    <div class="sk-card">
      <div class="sk-head">
        <span class="sk-block sk-line sk-line-label"></span>
        <span class="sk-block sk-pill"></span>
      </div>
      <span class="sk-block sk-line sk-line-title"></span>
      <span class="sk-block sk-line sk-line-meta"></span>
    </div>

    <div class="sk-card">
      <span class="sk-block sk-line sk-line-label"></span>
      <div v-for="n in rows" :key="n" class="sk-row">
        <span class="sk-block sk-mark"></span>
        <span class="sk-lines">
          <span class="sk-block sk-line sk-line-title"></span>
          <span class="sk-block sk-line sk-line-meta"></span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 3 },
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
  border-radius: var(--radius-lg);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface);
}
.sk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.sk-row {
  display: flex;
  align-items: center;
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
.sk-mark {
  height: var(--sp-8);
  width: var(--sp-8);
  flex-shrink: 0;
  border-radius: var(--radius);
}
.sk-line {
  height: var(--sp-3);
}
.sk-line-label {
  width: 30%;
}
.sk-line-value {
  width: 62%;
  height: var(--sp-5);
}
.sk-line-title {
  width: 72%;
}
.sk-line-meta {
  width: 44%;
}
.sk-pill {
  height: var(--sp-5);
  width: var(--sp-8);
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
