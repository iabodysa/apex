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
      <Button
        class="tap tap-pass"
        size="xl"
        variant="outline"
        :class="{ 'tap-on': verdict === 'pass' }"
        :aria-pressed="verdict === 'pass'"
        :label="t('round.due.pass')"
        @click="choose('pass')"
      >
        <template #prefix><Icon name="check" :size="18" /></template>
      </Button>
      <Button
        class="tap tap-fail"
        size="xl"
        variant="outline"
        :class="{ 'tap-on': verdict === 'fail' }"
        :aria-pressed="verdict === 'fail'"
        :label="t('round.due.fail')"
        @click="choose('fail')"
      >
        <template #prefix><Icon name="x" :size="18" /></template>
      </Button>
      <Button
        class="tap tap-issue"
        size="xl"
        variant="outline"
        :class="{ 'tap-on': verdict === 'issue' }"
        :aria-pressed="verdict === 'issue'"
        :label="t('round.due.issue')"
        @click="choose('issue')"
      >
        <template #prefix><Icon name="triangle-alert" :size="17" /></template>
      </Button>
      <Button
        class="tap tap-note"
        size="xl"
        variant="outline"
        :class="{ 'tap-on': noteOpen || hasNote }"
        :aria-pressed="noteOpen"
        :label="t('round.due.addNote')"
        @click="noteOpen = !noteOpen"
      >
        <template #prefix><Icon name="pencil" :size="16" /></template>
      </Button>
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
        <FormControl
          class="note-input"
          type="textarea"
          size="lg"
          :rows="2"
          :placeholder="t('round.due.notePlaceholder')"
          :model-value="notes"
          @update:model-value="$emit('note', $event)"
        />
        <p v-if="task.instructions" class="note-hint">
          <strong>{{ t("round.due.instructions") }}:</strong> {{ task.instructions }}
        </p>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, FileUploader, FormControl } from "frappe-ui";
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
  border-block-end: 1px solid var(--c-border);
  background: transparent;
  padding: var(--sp-4) var(--sp-1);
  padding-inline-start: var(--sp-3);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}
.task-pass {
  border-inline-start: 3px solid var(--c-success);
  background: color-mix(in srgb, var(--c-success-bg) 40%, transparent);
}
.task-fail {
  border-inline-start: 3px solid var(--c-danger);
  background: color-mix(in srgb, var(--c-danger-bg) 40%, transparent);
}
.task-issue {
  border-inline-start: 3px solid var(--c-warning);
  background: color-mix(in srgb, var(--c-warning-bg) 40%, transparent);
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}
.tap {
  min-block-size: var(--tap-min);
  color: var(--c-muted);
  transition:
    background 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;
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
.note-input :deep(textarea) { min-block-size: 5rem; }
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

@media (min-width: 42rem) {
  .task-actions {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
