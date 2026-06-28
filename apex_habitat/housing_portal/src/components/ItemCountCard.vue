<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- One inventory line: a numeric stepper that stages counted_quantity, a
     condition Select, and an optional note. The variance shown is the
     SERVER-DERIVED quantity_variance loaded with the row (read-only) — it is
     never recomputed on the client, so the displayed figure always matches what
     the Housing Inventory controller derived at the last save. -->
<template>
  <div class="item-card" :class="{ 'item-card-staged': staged }">
    <div class="item-head">
      <span class="item-mark"><Icon name="box" :size="18" /></span>
      <div class="item-id">
        <p class="item-name">{{ row.item_name }}</p>
        <p class="item-meta">
          <span>{{ tEnum("category", row.item_category) }}</span>
          <span v-if="row.uom" class="item-uom">· {{ row.uom }}</span>
        </p>
      </div>
      <span class="pill" :class="conditionPill">{{ tEnum("condition", model.condition) }}</span>
    </div>

    <!-- Expected / staged-counted / server variance, side by side. -->
    <div class="item-figures">
      <div class="figure">
        <span class="figure-label">{{ t("card.expected") }}</span>
        <span class="figure-value">{{ fmt(row.expected_quantity) }}</span>
      </div>
      <div class="figure">
        <span class="figure-label">{{ t("card.counted") }}</span>
        <span class="figure-value figure-strong">{{ fmt(model.counted_quantity) }}</span>
      </div>
      <div class="figure" :title="t('card.varianceHint')">
        <span class="figure-label">{{ t("card.variance") }}</span>
        <span class="figure-value" :class="varianceClass">{{ varianceText }}</span>
      </div>
    </div>

    <!-- Numeric stepper writes counted_quantity. -->
    <div class="stepper" role="group" :aria-label="t('card.counted')">
      <button type="button" class="step-btn" :aria-label="t('card.decrease')" @click="bump(-1)">
        <Icon name="minus" :size="20" />
      </button>
      <input
        class="step-input"
        type="number"
        inputmode="decimal"
        min="0"
        step="1"
        :value="model.counted_quantity"
        @input="onInput($event.target.value)"
      />
      <button type="button" class="step-btn" :aria-label="t('card.increase')" @click="bump(1)">
        <Icon name="plus" :size="20" />
      </button>
    </div>

    <!-- Condition Select (server-driven option set, labels via tEnum). -->
    <label class="field">
      <span class="field-label">{{ t("card.condition") }}</span>
      <select class="field-input" :value="model.condition" @change="onCondition($event.target.value)">
        <option v-for="c in conditions" :key="c" :value="c">{{ tEnum("condition", c) }}</option>
      </select>
    </label>

    <!-- Optional note. -->
    <label class="field">
      <span class="field-label">{{ t("common.note") }}</span>
      <textarea
        class="field-input field-textarea"
        rows="2"
        :value="model.notes"
        :placeholder="t('card.notePlaceholder')"
        @input="onNote($event.target.value)"
      ></textarea>
    </label>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, tEnum } = useI18n();

const props = defineProps({
  row: { type: Object, required: true },
  // Staged edit: { counted_quantity, condition, notes }.
  model: { type: Object, required: true },
  // The DocType's condition Select option set, passed from the server payload.
  conditions: { type: Array, default: () => [] },
  // True once the user has touched this row (so it is part of the submit set).
  staged: { type: Boolean, default: false },
});

const emit = defineEmits(["count", "condition", "note"]);

function fmt(v) {
  const n = Number(v || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");
}

function onInput(value) {
  let n = parseFloat(value);
  if (Number.isNaN(n) || n < 0) n = 0;
  emit("count", n);
}
function bump(delta) {
  const cur = Number(props.model.counted_quantity || 0);
  const next = Math.max(0, cur + delta);
  emit("count", next);
}
function onCondition(value) {
  emit("condition", value);
}
function onNote(value) {
  emit("note", value);
}

// Server-derived variance, rendered verbatim from the loaded row. A staged edit
// does NOT recompute it — the figure reflects the last server save and is
// refreshed when the row reloads after submit.
const variance = computed(() => Number(props.row.quantity_variance || 0));
const varianceText = computed(() => {
  const v = variance.value;
  return v > 0 ? "+" + fmt(v) : fmt(v);
});
const varianceClass = computed(() => {
  const v = variance.value;
  if (v < 0) return "figure-danger";
  if (v > 0) return "figure-warning";
  return "figure-muted";
});

const conditionPill = computed(() => {
  const c = props.model.condition;
  if (c === "Damaged" || c === "Missing") return "pill-danger";
  if (c === "Needs Maintenance" || c === "Fair") return "pill-warning";
  return "pill-success";
});
</script>

<style scoped>
.item-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  transition: border-color 0.15s ease;
}
.item-card-staged {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 1px var(--c-primary);
}
.item-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.item-mark {
  display: grid;
  place-items: center;
  height: 34px;
  width: 34px;
  border-radius: var(--radius);
  flex-shrink: 0;
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.item-id {
  flex: 1;
  min-width: 0;
}
.item-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-meta {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.item-uom {
  margin-inline-start: 2px;
}

.item-figures {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  text-align: center;
}
.figure {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 4px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-ink) 4%, transparent);
}
.figure-label {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.figure-value {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.figure-strong {
  color: var(--c-primary);
}
.figure-danger {
  color: var(--c-danger);
}
.figure-warning {
  color: var(--c-warning);
}
.figure-muted {
  color: var(--c-muted);
}

.stepper {
  display: flex;
  align-items: center;
  gap: 10px;
}
.step-btn {
  display: grid;
  place-items: center;
  height: 48px;
  width: 48px;
  flex-shrink: 0;
  border-radius: var(--radius);
  border: 1px solid var(--c-border-strong);
  background: var(--c-surface-2, var(--c-surface));
  color: var(--c-ink);
  cursor: pointer;
  transition: transform 0.06s ease;
}
.step-btn:active {
  transform: scale(0.95);
}
.step-input {
  flex: 1;
  min-width: 0;
  height: 48px;
  text-align: center;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-surface-2, var(--c-surface));
  color: var(--c-ink);
  font-family: var(--font);
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
}
.step-input:focus {
  outline: none;
  border-color: var(--c-primary);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-label {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
}
.field-input {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-surface-2, var(--c-surface));
  color: var(--c-ink);
  font-family: var(--font);
  font-size: var(--fs-body);
}
.field-input:focus {
  outline: none;
  border-color: var(--c-primary);
}
.field-textarea {
  resize: vertical;
}
</style>
