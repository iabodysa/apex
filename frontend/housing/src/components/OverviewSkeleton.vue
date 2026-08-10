<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="ov-sk" role="status" :aria-label="label">
    <div class="ov-sk-ribbon">
      <span v-for="n in 4" :key="n" class="sk-block ov-sk-metric"></span>
    </div>

    <div class="ov-sk-layout">
      <div class="ov-sk-lead card">
        <span class="sk-block ov-sk-kicker"></span>
        <span class="sk-block ov-sk-title"></span>
        <span class="sk-block ov-sk-title ov-sk-title-short"></span>
        <span class="sk-block ov-sk-copy"></span>
      </div>

      <div class="ov-sk-queue card card-flush">
        <span class="sk-block ov-sk-head"></span>
        <div v-for="n in 4" :key="n" class="ov-sk-row">
          <span class="sk-block ov-sk-icon"></span>
          <span class="ov-sk-lines">
            <span class="sk-block ov-sk-line"></span>
            <span class="sk-block ov-sk-line ov-sk-line-short"></span>
          </span>
          <span class="sk-block ov-sk-value"></span>
        </div>
      </div>
    </div>

    <div class="ov-sk-ledger">
      <span v-for="n in 3" :key="n" class="sk-block ov-sk-tile"></span>
    </div>
  </div>
</template>

<script setup>
/* DESIGN.md §7: a skeleton of the shape that is coming, never a spinner alone. This draws
   the overview it replaces — the metric ribbon, the lead panel beside the work queue, and
   the three domain tiles — at the same sizes, so nothing moves when the data lands. */
defineProps({
  label: { type: String, required: true },
});
</script>

<style scoped>
.ov-sk {
  display: flex;
  flex-direction: column;
  gap: clamp(var(--sp-6), 5vw, 4rem);
}
.sk-block {
  display: block;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-ink) 9%, transparent);
  animation: ov-sk-pulse 1.4s ease-in-out infinite;
}
.ov-sk-ribbon {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}
.ov-sk-metric {
  block-size: var(--tap-lg);
  border-radius: var(--radius);
}
.ov-sk-layout {
  display: grid;
  gap: clamp(var(--sp-5), 4vw, var(--sp-8));
}
.ov-sk-lead {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  align-self: start;
}
.ov-sk-kicker {
  inline-size: 40%;
  block-size: var(--sp-3);
}
.ov-sk-title {
  inline-size: 90%;
  block-size: var(--sp-6);
}
.ov-sk-title-short {
  inline-size: 62%;
}
.ov-sk-copy {
  inline-size: 78%;
  block-size: var(--sp-4);
}
.ov-sk-head {
  inline-size: 45%;
  block-size: var(--sp-5);
  margin-inline: var(--sp-4);
  margin-block-end: var(--sp-4);
}
.ov-sk-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: 72px;
  padding: var(--sp-3) var(--sp-4);
  border-block-start: var(--border-width) solid var(--c-border);
}
.ov-sk-icon {
  flex: 0 0 auto;
  inline-size: var(--tap-min);
  block-size: var(--tap-min);
  border-radius: var(--radius);
}
.ov-sk-lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--sp-2);
  min-inline-size: 0;
}
.ov-sk-line {
  inline-size: 70%;
  block-size: var(--sp-3);
}
.ov-sk-line-short {
  inline-size: 44%;
}
.ov-sk-value {
  flex: 0 0 auto;
  inline-size: var(--sp-8);
  block-size: var(--sp-5);
  border-radius: var(--radius-pill);
}
.ov-sk-ledger {
  display: grid;
  gap: var(--sp-3);
}
.ov-sk-tile {
  block-size: 76px;
  border-radius: var(--radius);
}

@keyframes ov-sk-pulse {
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

/* Mirrors the overview's own breakpoints so the skeleton and the content share one shape. */
@container mc-frame (min-width: 46rem) {
  .ov-sk-layout {
    grid-template-columns: minmax(18rem, 0.8fr) minmax(24rem, 1.2fr);
  }
}
@container mc-frame (min-width: 34rem) {
  .ov-sk-ledger {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
