<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="stepper">
    <button
      type="button"
      class="step-key"
      :disabled="disabled || modelValue <= min"
      :aria-label="t('card.decrease')"
      @click="emitValue(modelValue - 1)"
    >
      <Icon name="minus" :size="20" />
    </button>
    <input
      class="step-input mono"
      type="number"
      inputmode="numeric"
      :min="min"
      :max="max"
      :disabled="disabled"
      :aria-label="label || t('custody.qty')"
      :value="modelValue"
      @input="onInput"
    />
    <button
      type="button"
      class="step-key"
      :disabled="disabled || modelValue >= max"
      :aria-label="t('card.increase')"
      @click="emitValue(modelValue + 1)"
    >
      <Icon name="plus" :size="20" />
    </button>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  modelValue: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 9999 },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);
const { t } = useI18n();

function clamp(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return props.min;
  return Math.min(props.max, Math.max(props.min, Math.round(n)));
}

function emitValue(value) {
  emit("update:modelValue", clamp(value));
}

function onInput(event) {
  emitValue(event.target.value);
}
</script>

<style scoped>
.stepper {
  display: inline-flex;
  align-items: stretch;
  gap: var(--sp-2);
}
.step-key {
  display: grid;
  place-items: center;
  min-height: var(--tap-min);
  min-width: var(--tap-min);
  border-radius: var(--radius-sm);
  border: var(--border-width) solid var(--c-border-strong);
  background: var(--c-surface-2);
  color: var(--c-ink);
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.step-key:disabled {
  opacity: 0.45;
  cursor: default;
}
@media (hover: hover) {
  .step-key:hover:not(:disabled) {
    background: color-mix(in srgb, var(--c-ink) 6%, var(--c-surface-2));
  }
}
.step-key:focus-visible,
.step-input:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 1px;
}
.step-input {
  width: 68px;
  min-height: var(--tap-min);
  text-align: center;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  border-radius: var(--radius-sm);
  border: var(--border-width) solid var(--c-border-strong);
  background: var(--c-surface);
  color: var(--c-ink);
}
.step-input:disabled {
  opacity: 0.6;
}
</style>
