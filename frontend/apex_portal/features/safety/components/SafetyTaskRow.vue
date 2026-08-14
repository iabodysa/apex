<script setup>
import { computed, reactive, ref } from "vue";
import { Button, FileUploader, FormControl } from "frappe-ui";

const props = defineProps({ task: { type: Object, required: true } });
const emit = defineEmits(["change"]);
const result = reactive({
  task: props.task.name,
  cadence: props.task.cadence,
  execution_status: "",
  notes: "",
  evidence_photo: "",
});
const noteOpen = ref(false);
const failed = computed(() => ["Poor", "Not Done"].includes(result.execution_status));
const needsPhoto = computed(() => Boolean(props.task.evidence_required) && failed.value);

function changed() { emit("change", { ...result }); }
function choose(executionStatus) {
  result.execution_status = executionStatus;
  if (failed.value) noteOpen.value = true;
  changed();
}
function updateNotes(notes) {
  result.notes = notes;
  changed();
}
function uploaded(file) {
  result.evidence_photo = file.file_url;
  changed();
}
</script>

<template>
  <article
    class="feature-card safety-task"
    :data-status="result.execution_status || undefined"
  >
    <div>
      <strong dir="auto">{{ task.task_title || task.name }}</strong>
      <p v-if="task.instructions">{{ task.instructions }}</p>
    </div>
    <div class="safety-checklist__decisions" role="group" :aria-label="`نتيجة ${task.task_title || task.name}`">
      <Button
        class="safety-checklist__decision safety-checklist__decision--good"
        variant="outline"
        icon-left="lucide-check"
        :aria-pressed="result.execution_status === 'Good'"
        @click="choose('Good')"
      >سليم</Button>
      <Button
        class="safety-checklist__decision safety-checklist__decision--poor"
        variant="outline"
        icon-left="lucide-alert-triangle"
        :aria-pressed="result.execution_status === 'Poor'"
        @click="choose('Poor')"
      >يحتاج معالجة</Button>
      <Button
        class="safety-checklist__decision safety-checklist__decision--not-done"
        variant="outline"
        icon-left="lucide-minus-circle"
        :aria-pressed="result.execution_status === 'Not Done'"
        @click="choose('Not Done')"
      >لم يُفحص</Button>
    </div>
    <Button
      class="safety-checklist__note-toggle"
      variant="subtle"
      :aria-expanded="noteOpen"
      @click="noteOpen = !noteOpen"
    >{{ result.notes ? 'تعديل الملاحظة' : 'إضافة ملاحظة' }}</Button>
    <FormControl
      v-if="noteOpen"
      :model-value="result.notes"
      type="textarea"
      label="ملاحظات"
      @update:model-value="updateNotes"
    />
    <div v-if="needsPhoto" class="safety-checklist__evidence">
      <FileUploader
        :file-types="['image/*']"
        :upload-args="{ private: 1, folder: 'Home/Attachments' }"
        @success="uploaded"
      >
        <template #default="{ openFileSelector, uploading }">
          <Button variant="subtle" :loading="uploading" @click="openFileSelector">
            {{ result.evidence_photo ? 'تغيير الصورة' : 'إرفاق صورة' }}
          </Button>
        </template>
      </FileUploader>
      <small>{{ result.evidence_photo ? 'تم إرفاق الصورة.' : 'الصورة مطلوبة لهذا البند.' }}</small>
    </div>
  </article>
</template>
