<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Horizontal trip status progress bar: shows the trip lifecycle as coloured steps.
     Used in the worker (Masar) Transport page for upcoming/active trips. -->
<template>
  <div class="progress-bar" :dir="dir">
    <div
      v-for="(step, i) in steps"
      :key="step.key"
      class="progress-step"
      :class="{
        'progress-step-done': step.reached,
        'progress-step-active': step.active,
      }"
    >
      <div class="progress-dot">
        <svg v-if="step.reached && !step.active" class="progress-check" viewBox="0 0 16 16" fill="none">
          <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <div v-else-if="step.active" class="progress-pulse"></div>
        <span v-else class="progress-num">{{ i + 1 }}</span>
      </div>
      <span class="progress-label">{{ step.label }}</span>
      <div v-if="i < steps.length - 1" class="progress-connector" :class="{ 'progress-connector-done': step.reached }"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useI18n } from "../i18n";

const { t, dir } = useI18n();

const props = defineProps({
  status: { type: String, default: "" },
});

const STATUS_ORDER = ["Planned", "Dispatched", "Started", "Completed"];

const steps = computed(() => {
  const currentIdx = STATUS_ORDER.indexOf(props.status);
  return STATUS_ORDER.map((key, i) => ({
    key,
    label: t(`tripProgress.${key}`),
    reached: i <= currentIdx,
    active: i === currentIdx && key !== "Completed",
  }));
});
</script>

<style scoped>
.progress-bar {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 8px 0;
  overflow-x: auto;
}

.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
  min-width: 0;
}

.progress-dot {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  border: 2px solid var(--c-border-strong, #d1d5db);
  background: var(--c-surface, #fff);
  color: var(--c-muted, #9ca3af);
  transition: all 0.3s ease;
  position: relative;
  z-index: 1;
}

.progress-step-done .progress-dot {
  background: var(--c-success, var(--brand-green));
  border-color: var(--c-success, var(--brand-green));
  color: #fff;
}

.progress-step-active .progress-dot {
  background: var(--c-primary, #2563eb);
  border-color: var(--c-primary, #2563eb);
  color: #fff;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-primary, #2563eb) 20%, transparent);
}

.progress-label {
  margin-top: 6px;
  font-size: 10px;
  font-weight: 600;
  color: var(--c-muted, #9ca3af);
  text-align: center;
  white-space: nowrap;
}

.progress-step-done .progress-label,
.progress-step-active .progress-label {
  color: var(--c-ink, #1f2937);
}

.progress-connector {
  position: absolute;
  top: 12px;
  left: 50%;
  width: 100%;
  height: 3px;
  background: var(--c-border-strong, #d1d5db);
  z-index: 0;
  transition: background 0.4s ease;
}

.progress-connector-done {
  background: var(--c-success, var(--brand-green));
}

[dir="rtl"] .progress-connector {
  left: auto;
  right: 50%;
}

.progress-pulse {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.progress-check {
  width: 12px;
  height: 12px;
}

.progress-num {
  line-height: 1;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.7); }
}
</style>
