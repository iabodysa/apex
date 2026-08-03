<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="editor">
    <header class="editor-head">
      <span v-if="heading" class="editor-mark"><Icon name="box" :size="24" /></span>
      <div class="editor-id">
        <h2 v-if="heading" class="editor-name">{{ row.item_name }}</h2>
        <p class="editor-meta">
          <span>{{ tEnum("category", row.item_category) }}</span>
          <template v-if="row.uom">
            <span aria-hidden="true">·</span>
            <span>{{ row.uom }}</span>
          </template>
          <template v-if="roomLabel">
            <span aria-hidden="true">·</span>
            <span>{{ roomLabel }}</span>
          </template>
        </p>
      </div>
    </header>

    <dl class="figures">
      <div class="figure">
        <dt class="figure-label">{{ t("card.expected") }}</dt>
        <dd class="figure-value"><bdi class="mono">{{ fmt(row.expected_quantity) }}</bdi></dd>
      </div>
      <div class="figure">
        <dt class="figure-label">{{ t("card.counted") }}</dt>
        <dd class="figure-value figure-strong"><bdi class="mono">{{ fmt(model.counted_quantity) }}</bdi></dd>
      </div>
      <Tooltip :text="t('card.varianceHint')">
        <div class="figure">
          <dt class="figure-label">{{ t("card.variance") }}</dt>
          <dd class="figure-value" :class="varianceClass"><bdi class="mono">{{ varianceText }}</bdi></dd>
        </div>
      </Tooltip>
    </dl>

    <div class="stepper" role="group" :aria-label="t('card.countLabel')">
      <Button
        size="2xl"
        variant="outline"
        class="step-btn"
        :aria-label="t('card.decrease')"
        @click="bump(-1)"
      >
        <template #icon><Icon name="minus" :size="24" /></template>
      </Button>
      <FormControl
        class="step-field"
        type="number"
        size="lg"
        min="0"
        step="1"
        inputmode="decimal"
        :aria-label="t('card.countLabel')"
        :modelValue="model.counted_quantity"
        @update:modelValue="onInput"
      />
      <Button
        size="2xl"
        variant="outline"
        class="step-btn"
        :aria-label="t('card.increase')"
        @click="bump(1)"
      >
        <template #icon><Icon name="plus" :size="24" /></template>
      </Button>
    </div>

    <FormControl
      class="editor-field"
      type="select"
      size="lg"
      :label="t('card.condition')"
      :options="conditionOptions"
      :modelValue="model.condition"
      @update:modelValue="$emit('condition', $event)"
    />

    <FormControl
      class="editor-field"
      type="textarea"
      size="lg"
      :rows="3"
      :label="t('common.note')"
      dir="auto"
      :placeholder="t('card.notePlaceholder')"
      :modelValue="model.notes"
      @update:modelValue="$emit('note', $event)"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Button, FormControl, Tooltip } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, tEnum } = useI18n();

const props = defineProps({
  row: { type: Object, required: true },
  model: { type: Object, required: true },
  conditions: { type: Array, default: () => [] },
  roomLabel: { type: String, default: "" },
  heading: { type: Boolean, default: true },
});

const emit = defineEmits(["count", "condition", "note"]);

function fmt(v) {
  const n = Number(v || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");
}

const conditionOptions = computed(() =>
  props.conditions.map((c) => ({ label: tEnum("condition", c), value: c })),
);

function onInput(value) {
  let n = parseFloat(value);
  if (Number.isNaN(n) || n < 0) n = 0;
  emit("count", n);
}

function bump(delta) {
  emit("count", Math.max(0, Number(props.model.counted_quantity || 0) + delta));
}

const variance = computed(
  () => Number(props.model.counted_quantity || 0) - Number(props.row.expected_quantity || 0),
);
const varianceText = computed(() => (variance.value > 0 ? "+" + fmt(variance.value) : fmt(variance.value)));
const varianceClass = computed(() => {
  if (variance.value < 0) return "figure-danger";
  if (variance.value > 0) return "figure-warning";
  return "figure-ok";
});
</script>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.editor-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.editor-mark {
  display: grid;
  place-items: center;
  height: var(--tap-md);
  width: var(--tap-md);
  flex-shrink: 0;
  border-radius: var(--radius);
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.editor-id {
  min-width: 0;
}
.editor-name {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.2;
}
.editor-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
  margin-top: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--c-muted);
}

.figures {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-2);
  margin: 0;
}
.figure {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding: var(--sp-3) var(--sp-2);
  border-radius: var(--radius-sm);
  text-align: center;
  background: color-mix(in srgb, var(--c-ink) 4%, transparent);
}
.figure-label {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.figure-value {
  margin: 0;
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.figure-strong {
  color: var(--c-primary);
}
.figure-ok {
  color: var(--c-success);
}
.figure-warning {
  color: var(--c-warning);
}
.figure-danger {
  color: var(--c-danger);
}

.stepper {
  display: flex;
  align-items: stretch;
  gap: var(--sp-3);
}
.step-btn {
  flex-shrink: 0;
}
.step-field {
  flex: 1;
  min-width: 0;
}
</style>
