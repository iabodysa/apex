<script setup>
import { reactive, watch } from "vue";
import { Button, FileUploader, FormControl } from "frappe-ui";

const props = defineProps({ task: { type: Object, required: true } });
const emit = defineEmits(["change"]);
const result = reactive({
  task: props.task.name,
  cadence: props.task.cadence,
  execution_status: "Good",
  notes: "",
  evidence_photo: "",
});

watch(result, () => emit("change", { ...result }), { deep: true, immediate: true });
function uploaded(file) { result.evidence_photo = file.file_url; }
</script>

<template>
  <article class="feature-card safety-task">
    <div>
      <strong dir="auto">{{ task.task_title || task.name }}</strong>
      <p v-if="task.instructions">{{ task.instructions }}</p>
    </div>
    <FormControl
      v-model="result.execution_status"
      type="select"
      label="النتيجة"
      :options="[
        { label: 'ممتاز', value: 'Excellent' },
        { label: 'جيد', value: 'Good' },
        { label: 'متوسط', value: 'Average' },
        { label: 'ضعيف', value: 'Poor' },
        { label: 'لم ينفذ', value: 'Not Done' },
      ]"
    />
    <FormControl v-model="result.notes" type="textarea" label="ملاحظات" />
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
    <small v-if="task.evidence_required">الصورة مطلوبة عند تسجيل ملاحظة.</small>
  </article>
</template>
