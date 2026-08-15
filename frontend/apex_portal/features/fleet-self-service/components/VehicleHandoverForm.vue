<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Button, FileUploader, FormControl, createResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { createSingleFlight } from "../state.js";
import {
  buildHandoverPayload,
  inspectionRowsFromTemplate,
  isInspectionComplete,
} from "../handoverState.js";

const props = defineProps({
  direction: { type: String, required: true, validator: (value) => ["Receipt", "Return"].includes(value) },
  title: { type: String, required: true },
  intro: { type: String, required: true },
});
const emit = defineEmits(["saved"]);

const checklist = createResource({
  url: "apex.salis.api.fleet_employee_services.get_handover_checklist",
  method: "GET",
  auto: false,
});
const action = createResource({
  url: props.direction === "Receipt"
    ? "apex.salis.api.fleet_employee_services.receive_vehicle"
    : "apex.salis.api.fleet_employee_services.return_vehicle",
  method: "POST",
  auto: false,
});
const form = reactive({
  odometer: "",
  fuel_level: "",
  condition_notes: "",
  signed_evidence: "",
});
const checklistData = ref(null);
const rows = ref([]);
const loadingChecklist = ref(true);
const checklistError = ref("");
const submitError = ref("");
const notice = ref("");
const saving = ref(false);
const submitted = ref(false);
const submitOnce = createSingleFlight();
const actionKey = computed(() => `vehicle-handover-${props.direction.toLowerCase()}`);
const canSubmit = computed(() => !submitted.value
  && form.odometer !== ""
  && form.signed_evidence
  && checklistData.value?.template
  && isInspectionComplete(rows.value));
const missingTemplateHelp = computed(() => props.direction === "Receipt"
  ? "لا يوجد قالب فحص نشط للاستلام. اطلب من مسؤول الأسطول تفعيل قالب الاستلام ثم أعد المحاولة."
  : "لا يوجد قالب فحص نشط للإرجاع. اطلب من مسؤول الأسطول تفعيل قالب الإرجاع ثم أعد المحاولة.");

async function loadChecklist() {
  loadingChecklist.value = true;
  checklistError.value = "";
  checklistData.value = null;
  rows.value = [];
  try {
    const result = await checklist.fetch({ direction: props.direction });
    const data = result?.message || result;
    if (!data?.template || !Array.isArray(data.items) || !data.items.length) {
      throw new Error(missingTemplateHelp.value);
    }
    checklistData.value = data;
    rows.value = inspectionRowsFromTemplate(data.items);
  } catch (reason) {
    checklistError.value = safeErrorMessage(reason, missingTemplateHelp.value);
  } finally {
    loadingChecklist.value = false;
  }
}

function decide(row, ok) {
  row.ok = ok;
  if (ok) row.remark = "";
}

function onUploaded(result) {
  form.signed_evidence = result?.file_url || "";
}

async function submit() {
  if (!canSubmit.value || saving.value) return;
  submitError.value = "";
  notice.value = "";
  saving.value = true;
  try {
    const payload = buildHandoverPayload(form, checklistData.value, rows.value);
    const result = await submitOnce(actionKey.value, () => action.submit(payload));
    submitted.value = true;
    notice.value = props.direction === "Receipt"
      ? "تم تسجيل استلام المركبة والفحص الموقّع."
      : "تم تسجيل إرجاع المركبة والفحص الموقّع.";
    emit("saved", result);
  } catch (reason) {
    submitError.value = safeErrorMessage(reason, "تعذّر حفظ الفحص. بقيت إجاباتك ويمكنك المحاولة مرة أخرى.");
  } finally {
    saving.value = false;
  }
}

onMounted(loadChecklist);
</script>

<template>
  <section class="salis-page salis-form-page vehicle-handover" :aria-busy="loadingChecklist">
    <header>
      <p class="salis-eyebrow">ساليس</p>
      <h2>{{ title }}</h2>
      <p>{{ intro }}</p>
    </header>

    <PortalSkeleton v-if="loadingChecklist" :rows="4" label="جارٍ تحميل قالب الفحص المعتمد" />
    <PortalErrorState
      v-else-if="checklistError"
      title="تعذّر بدء فحص المركبة"
      :message="checklistError"
      :fallback="missingTemplateHelp"
      @retry="loadChecklist"
    />
    <form v-else class="salis-form" @submit.prevent="submit">
      <section class="vehicle-handover__context">
        <div class="record-identity">
          <strong>قالب الفحص المعتمد</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ checklistData.template }}</bdi>
        </div>
        <bdi v-if="checklistData.vehicle" dir="auto" translate="no">{{ checklistData.vehicle }}</bdi>
      </section>

      <FormControl v-model="form.odometer" type="number" size="lg" label="قراءة العداد" min="0" required />
      <FormControl
        v-model="form.fuel_level"
        type="select"
        size="lg"
        label="مستوى الوقود"
        :options="[
          { label: 'اختر المستوى', value: '' },
          { label: 'فارغ', value: 'Empty' },
          { label: 'ربع', value: 'Quarter' },
          { label: 'نصف', value: 'Half' },
          { label: 'ثلاثة أرباع', value: 'Three Quarters' },
          { label: 'ممتلئ', value: 'Full' },
        ]"
      />

      <fieldset class="vehicle-handover__checklist">
        <legend>نتائج الفحص</legend>
        <article v-for="(row, index) in rows" :key="`${index}:${row.check_item}`" class="vehicle-handover__item">
          <div class="record-identity">
            <strong dir="auto">{{ row.check_item }}</strong>
            <span>البند {{ index + 1 }} من {{ rows.length }}</span>
          </div>
          <div class="vehicle-handover__decisions" role="group" :aria-label="`نتيجة ${row.check_item}`">
            <Button type="button" variant="outline" :aria-pressed="row.ok === true" @click="decide(row, true)">سليم</Button>
            <Button type="button" variant="outline" :aria-pressed="row.ok === false" @click="decide(row, false)">غير سليم</Button>
          </div>
          <FormControl
            v-if="row.ok === false"
            v-model="row.remark"
            type="textarea"
            :label="`ملاحظة العطل — ${row.check_item}`"
            :placeholder="row.default_remark || 'صف الحالة غير السليمة'"
            rows="2"
            required
          />
        </article>
      </fieldset>

      <FormControl v-model="form.condition_notes" type="textarea" size="lg" rows="3" label="ملاحظات عامة على الحالة" />
      <FileUploader
        :file-types="['image/*', 'application/pdf']"
        :upload-args="{ private: 1, folder: 'Home/Attachments' }"
        @success="onUploaded"
      >
        <template #default="{ openFileSelector, uploading, error: uploadError }">
          <div class="salis-upload vehicle-handover__evidence">
            <strong>الإثبات الموقّع <span aria-hidden="true">*</span></strong>
            <Button type="button" variant="outline" :loading="uploading" @click="openFileSelector">
              {{ form.signed_evidence ? 'تم إرفاق الإثبات' : 'إرفاق الإثبات الموقّع' }}
            </Button>
            <bdi v-if="form.signed_evidence" class="record-reference" dir="auto" translate="no">{{ form.signed_evidence }}</bdi>
            <p v-if="uploadError" class="salis-error" role="alert">تعذّر رفع الإثبات. حاول مرة أخرى.</p>
          </div>
        </template>
      </FileUploader>

      <p v-if="notice" class="salis-notice" role="status">{{ notice }}</p>
      <p v-if="submitError" class="salis-error" role="alert">{{ submitError }}</p>
      <Button type="submit" variant="solid" theme="green" size="lg" :loading="saving" :disabled="!canSubmit || saving">
        {{ direction === 'Receipt' ? 'تأكيد الاستلام' : 'تأكيد الإرجاع' }}
      </Button>
    </form>
  </section>
</template>
