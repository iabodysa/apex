<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="stepper" :dir="dir">
    <template v-for="(stop, i) in stops" :key="i">
      <div
        v-if="i > 0"
        class="stepper-line"
        :class="stop.done ? 'stepper-line-done' : ''"
      ></div>
      <div
        class="stepper-dot"
        :class="stop.done ? 'stepper-dot-done' : ''"
        :title="stop.stop_name || ''"
      >
        <svg v-if="stop.done" class="stepper-check" viewBox="0 0 16 16" fill="none">
          <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" />
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
  border-radius: var(--radius-pill);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  border: 2px solid var(--c-border-strong);
  background: var(--c-surface);
  color: var(--c-muted);
  transition:
    background-color 0.3s ease,
    border-color 0.3s ease,
    color 0.3s ease;
}

.stepper-dot-done {
  background: var(--c-success);
  border-color: var(--c-success);
  color: var(--c-primary-ink);
}

.stepper-line {
  flex: 1;
  min-width: 16px;
  height: 3px;
  border-radius: var(--radius-pill);
  background: var(--c-border-strong);
  transition: background 0.4s ease;
}

.stepper-line-done {
  background: var(--c-success);
}

.stepper-num {
  line-height: 1;
}

.stepper-check {
  width: 14px;
  height: 14px;
}
</style>
