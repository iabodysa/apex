<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- One checklist task as a fast-tap row. Three big targets — Pass (green check),
     Fail (red x), Issue (amber triangle) — plus a pencil that expands an inline
     note. The whole row tints to the chosen verdict; a tap scales the button
     (tactile feedback). Unrated rows read as neutral with a dashed status dot.

     Verdict -> execution_status mapping is OWNED here and surfaced via the
     `rate` event so App.vue builds the submit payload from one source:
        pass  -> "Good"      fail -> "Not Done"      issue -> "Poor"
-->
<template>
  <div class="task" :class="stateClass">
    <div class="task-main">
      <span class="task-status" aria-hidden="true">
        <Icon v-if="verdict === 'pass'" name="check" :size="16" />
        <Icon v-else-if="verdict === 'fail'" name="x" :size="16" />
        <Icon v-else-if="verdict === 'issue'" name="triangle-alert" :size="15" />
        <span v-else class="task-status-dot"></span>
      </span>

      <div class="task-text">
        <p class="task-title">{{ title }}</p>
        <div class="task-meta">
          <span v-if="task.task_code" class="task-code">{{ task.task_code }}</span>
          <span v-if="task.priority" class="pill" :class="priorityPill">{{ priorityLabel }}</span>
          <span v-if="task.evidence_required" class="task-evidence">
            <Icon name="flag" :size="12" /> {{ t("due.evidence") }}
          </span>
        </div>
      </div>
    </div>

    <div class="task-actions">
      <button
        type="button"
        class="tap tap-pass"
        :class="{ 'tap-on': verdict === 'pass' }"
        :aria-pressed="verdict === 'pass'"
        :aria-label="t('due.pass')"
        @click="choose('pass')"
      >
        <Icon name="check" :size="22" />
      </button>
      <button
        type="button"
        class="tap tap-fail"
        :class="{ 'tap-on': verdict === 'fail' }"
        :aria-pressed="verdict === 'fail'"
        :aria-label="t('due.fail')"
        @click="choose('fail')"
      >
        <Icon name="x" :size="22" />
      </button>
      <button
        type="button"
        class="tap tap-issue"
        :class="{ 'tap-on': verdict === 'issue' }"
        :aria-pressed="verdict === 'issue'"
        :aria-label="t('due.issue')"
        @click="choose('issue')"
      >
        <Icon name="triangle-alert" :size="20" />
      </button>
      <button
        type="button"
        class="tap tap-note"
        :class="{ 'tap-on': noteOpen || hasNote }"
        :aria-pressed="noteOpen"
        :aria-label="t('due.addNote')"
        @click="noteOpen = !noteOpen"
      >
        <Icon name="pencil" :size="18" />
      </button>
    </div>

    <Transition name="note">
      <div v-if="noteOpen" class="task-note">
        <textarea
          :value="notes"
          class="note-input"
          rows="2"
          :placeholder="t('due.notePlaceholder')"
          @input="$emit('note', $event.target.value)"
        ></textarea>
        <p v-if="task.instructions" class="note-hint">
          <strong>{{ t("due.instructions") }}:</strong> {{ task.instructions }}
        </p>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  task: { type: Object, required: true },
  // current verdict: "" | "pass" | "fail" | "issue"
  verdict: { type: String, default: "" },
  notes: { type: String, default: "" },
});

const emit = defineEmits(["rate", "note"]);
const { t, tEnum } = useI18n();

const noteOpen = ref(false);
const hasNote = computed(() => !!(props.notes && props.notes.trim()));

// task_title is the English source string; Arabic is served by the translation
// layer. One title field, translated — no parallel English column.
const title = computed(() => props.task.task_title || props.task.name);

const priorityLabel = computed(() => tEnum("priority", props.task.priority));
const priorityPill = computed(() => {
  switch (props.task.priority) {
    case "Critical":
      return "pill-danger";
    case "High":
      return "pill-warning";
    default:
      return "pill-neutral";
  }
});

const stateClass = computed(() => (props.verdict ? "task-" + props.verdict : ""));

// Tapping the active verdict again clears it (toggle); otherwise set it.
function choose(next) {
  emit("rate", props.verdict === next ? "" : next);
}
</script>

<style scoped>
.task {
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  padding: 12px 12px 12px 14px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}
.task-pass {
  border-color: color-mix(in srgb, var(--c-success) 45%, transparent);
  background: color-mix(in srgb, var(--c-success-bg) 55%, var(--c-surface));
}
.task-fail {
  border-color: color-mix(in srgb, var(--c-danger) 45%, transparent);
  background: color-mix(in srgb, var(--c-danger-bg) 55%, var(--c-surface));
}
.task-issue {
  border-color: color-mix(in srgb, var(--c-warning) 45%, transparent);
  background: color-mix(in srgb, var(--c-warning-bg) 55%, var(--c-surface));
}

.task-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.task-status {
  display: grid;
  place-items: center;
  height: 22px;
  width: 22px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--c-muted);
  background: color-mix(in srgb, var(--c-ink) 6%, transparent);
}
.task-pass .task-status {
  color: var(--c-primary-ink);
  background: var(--c-success);
}
.task-fail .task-status {
  color: #fff;
  background: var(--c-danger);
}
.task-issue .task-status {
  color: #fff;
  background: var(--c-warning);
}
.task-status-dot {
  height: 7px;
  width: 7px;
  border-radius: 999px;
  border: 1.5px dashed var(--c-muted);
}
.task-text {
  min-width: 0;
  flex: 1;
}
.task-title {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.35;
}
.task-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
}
.task-code {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.03em;
}
.task-evidence {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-warning);
}

.task-actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.tap {
  display: grid;
  place-items: center;
  min-height: 48px;
  border-radius: var(--radius);
  border: 1.5px solid var(--c-border-strong);
  background: var(--c-surface-2, var(--c-surface));
  color: var(--c-muted);
  cursor: pointer;
  transition:
    transform 0.08s ease,
    background 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;
}
.tap:active {
  transform: scale(0.92);
}
.tap-pass.tap-on {
  background: var(--c-success);
  border-color: var(--c-success);
  color: var(--c-primary-ink);
}
.tap-fail.tap-on {
  background: var(--c-danger);
  border-color: var(--c-danger);
  color: #fff;
}
.tap-issue.tap-on {
  background: var(--c-warning);
  border-color: var(--c-warning);
  color: #fff;
}
.tap-note.tap-on {
  background: color-mix(in srgb, var(--c-ink) 88%, transparent);
  border-color: var(--c-ink);
  color: var(--c-surface);
}

.task-note {
  margin-top: 10px;
  overflow: hidden;
}
.note-input {
  width: 100%;
  background: var(--c-surface);
  color: var(--c-ink);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius-sm);
  padding: 9px 11px;
  font-family: var(--font);
  font-size: var(--fs-sm);
  line-height: 1.4;
  resize: vertical;
}
.note-input:focus {
  outline: none;
  border-color: var(--c-primary);
}
.note-input::placeholder {
  color: var(--c-muted);
}
.note-hint {
  margin-top: 6px;
  font-size: var(--fs-xs);
  color: var(--c-ink-soft);
  line-height: 1.5;
}

/* Inline note slide/fade. */
.note-enter-active,
.note-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.note-enter-from,
.note-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
