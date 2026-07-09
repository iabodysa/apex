<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Horizontal stop-progress stepper: a row of numbered dots connected by lines,
     coloring completed stops green. Used on the per-trip Route drill-in. -->
<template>
  <div class="stepper" :dir="dir">
    <template v-for="(stop, i) in stops" :key="i">
      <!-- Connecting line (not before the first dot) -->
      <div
        v-if="i > 0"
        class="stepper-line"
        :class="stop.done ? 'stepper-line-done' : ''"
      ></div>
      <!-- Stop dot -->
      <div
        class="stepper-dot"
        :class="stop.done ? 'stepper-dot-done' : ''"
        :title="stop.stop_name || ''"
      >
        <svg v-if="stop.done" class="stepper-check" viewBox="0 0 16 16" fill="none">
          <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span v-else class="stepper-num">{{ stop.sequence || i + 1 }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { useI18n } from "../i18n";
const { dir } = useI18n();

defineProps({
  stops: { type: Array, required: true },
});
</script>

<style scoped>
.stepper {
  display: flex;
  align-items: center;
  padding: 10px 4px;
  overflow-x: auto;
  gap: 0;
}

.stepper-dot {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  border: 2px solid var(--c-border-strong, #d1d5db);
  background: var(--c-surface, #fff);
  color: var(--c-muted, #9ca3af);
  transition: all 0.3s ease;
}

.stepper-dot-done {
  background: var(--c-success, #00844e);
  border-color: var(--c-success, #00844e);
  color: #fff;
}

.stepper-line {
  flex: 1;
  min-width: 16px;
  height: 3px;
  border-radius: 2px;
  background: var(--c-border-strong, #d1d5db);
  transition: background 0.4s ease;
}

.stepper-line-done {
  background: var(--c-success, #00844e);
}

.stepper-num {
  line-height: 1;
}

.stepper-check {
  width: 14px;
  height: 14px;
}
</style>
