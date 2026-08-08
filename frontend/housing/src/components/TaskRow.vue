<!-- Copyright (c) 2026, afmcoltd -->
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
            <Icon name="flag" :size="12" /> {{ t("round.due.evidence") }}
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
        :aria-label="t('round.due.pass')"
        @click="choose('pass')"
      >
        <Icon name="check" :size="22" />
      </button>
      <button
        type="button"
        class="tap tap-fail"
        :class="{ 'tap-on': verdict === 'fail' }"
        :aria-pressed="verdict === 'fail'"
        :aria-label="t('round.due.fail')"
        @click="choose('fail')"
      >
        <Icon name="x" :size="22" />
      </button>
      <button
        type="button"
        class="tap tap-issue"
        :class="{ 'tap-on': verdict === 'issue' }"
        :aria-pressed="verdict === 'issue'"
        :aria-label="t('round.due.issue')"
        @click="choose('issue')"
      >
        <Icon name="triangle-alert" :size="20" />
      </button>
      <button
        type="button"
        class="tap tap-note"
        :class="{ 'tap-on': noteOpen || hasNote }"
        :aria-pressed="noteOpen"
        :aria-label="t('round.due.addNote')"
        @click="noteOpen = !noteOpen"
      >
        <Icon name="pencil" :size="18" />
      </button>
    </div>

    <div v-if="needsPhoto" class="task-photo">
      <p v-if="!photo" class="task-photo-need">
        <Icon name="image" :size="13" /> {{ t("round.due.photoNeeded") }}
      </p>
      <div class="task-photo-row">
        <img v-if="photo" class="task-photo-thumb" :src="photo" alt="" />
        <FileUploader
          :file-types="PHOTO_ACCEPT"
          :validate-file="validatePhoto"
          :upload-args="{ private: 1, folder: 'Home/Attachments' }"
          @success="onUploaded"
        >
          <template #default="{ openFileSelector, uploading, error }">
            <div class="task-photo-actions">
              <Button
                size="lg"
                variant="outline"
                :loading="uploading"
                :loading-text="t('round.due.photoUploading')"
                :label="photo ? t('round.due.photoAttached') : t('round.due.addPhoto')"
                @click="openFileSelector"
              >
                <template #prefix><Icon name="image" :size="16" /></template>
              </Button>
              <Button
                v-if="photo"
                size="lg"
                variant="ghost"
                :label="t('round.due.removePhoto')"
                @click="$emit('photo', '')"
              />
              <p v-if="error" class="status-note status-err">{{ t("round.due.photoFailed") }}</p>
            </div>
          </template>
        </FileUploader>
      </div>
    </div>

    <Transition name="note">
      <div v-if="noteOpen" class="task-note">
        <textarea
          :value="notes"
          class="note-input"
          rows="2"
          :placeholder="t('round.due.notePlaceholder')"
          @input="$emit('note', $event.target.value)"
        ></textarea>
        <p v-if="task.instructions" class="note-hint">
          <strong>{{ t("round.due.instructions") }}:</strong> {{ task.instructions }}
        </p>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, FileUploader } from "frappe-ui";
import Icon from "./Icon.vue";
import { PHOTO_ACCEPT, isAcceptedPhoto } from "@shared/photoFile.js";
import { useI18n } from "../i18n";

const props = defineProps({
  task: { type: Object, required: true },
  verdict: { type: String, default: "" },
  notes: { type: String, default: "" },
  photo: { type: String, default: "" },
});

const emit = defineEmits(["rate", "note", "photo"]);
const { t, tEnum } = useI18n();

const noteOpen = ref(false);
const hasNote = computed(() => !!(props.notes && props.notes.trim()));

const title = computed(() => props.task.task_title || props.task.name);

const needsPhoto = computed(
  () => !!props.task.evidence_required && (props.verdict === "fail" || props.verdict === "issue"),
);

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

function choose(next) {
  emit("rate", props.verdict === next ? "" : next);
}

function validatePhoto(file) {
  return isAcceptedPhoto(file) ? null : t("round.due.photoWrongType");
}

function onUploaded(file) {
  emit("photo", (file && file.file_url) || "");
}
</script>

<style scoped>
.task {
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  padding: 12px;
  padding-inline-start: 14px;
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
  color: var(--c-danger-ink);
  background: var(--c-danger);
}
.task-issue .task-status {
  color: var(--c-warning-fill-ink);
  background: var(--c-warning-fill);
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
  min-height: var(--tap-min);
  border-radius: var(--radius);
  border: 1.5px solid var(--c-border-strong);
  background: var(--c-surface-2);
  color: var(--c-muted);
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  transition:
    transform 0.08s ease,
    background 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;
}
.tap:active {
  transform: scale(0.92);
}
@media (hover: hover) {
  .tap:hover:not(.tap-on) {
    background: color-mix(in srgb, var(--c-ink) 6%, var(--c-surface-2));
    color: var(--c-ink-soft);
  }
}
.tap-pass.tap-on {
  background: var(--c-success);
  border-color: var(--c-success);
  color: var(--c-primary-ink);
}
.tap-fail.tap-on {
  background: var(--c-danger);
  border-color: var(--c-danger);
  color: var(--c-danger-ink);
}
.tap-issue.tap-on {
  background: var(--c-warning-fill);
  border-color: var(--c-warning-fill);
  color: var(--c-warning-fill-ink);
}
.tap-note.tap-on {
  background: color-mix(in srgb, var(--c-ink) 88%, transparent);
  border-color: var(--c-ink);
  color: var(--c-surface);
}

.task-photo {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-photo-need {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-warning);
}
.task-photo-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.task-photo-thumb {
  height: 56px;
  width: 56px;
  border-radius: var(--radius-sm);
  object-fit: cover;
}
.task-photo-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.task-photo-actions :deep(button) {
  min-height: var(--tap-min);
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
.note-input:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 2px;
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
