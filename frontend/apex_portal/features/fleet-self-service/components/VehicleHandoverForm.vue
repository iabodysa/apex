<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Button, FileUploader, FormControl, createResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";
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
const missingTemplateHelp = computed(() => props.direction === "Receipt"
  ? __("No active inspection template exists for receipt. Ask the fleet administrator to activate the receipt template, then try again.")
  : __("No active inspection template exists for return. Ask the fleet administrator to activate the return template, then try again."));
// A driver standing at the vehicle reads five preconditions as one grey button. The checklist is
// the one worth naming: an unanswered item sits far up a long scrolled form, and a "غير سليم" item
// still owed its note looks answered. `canSubmit` is the reason's negation so they cannot drift.
const submitReason = computed(() => {
  if (submitted.value) return __("This inspection has already been recorded.");
  if (!checklistData.value?.template) return missingTemplateHelp.value;
  if (form.odometer === "") return __("Enter the odometer reading.");
  if (!isInspectionComplete(rows.value)) return __("Answer every inspection item, and write a note for every item that is not OK.");
  if (!form.signed_evidence) return __("Attach the signed evidence.");
  return "";
});
const canSubmit = computed(() => !submitReason.value);

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
    // The missing-template sentence is thrown above and travels as the reason's own message, so
    // it still reaches the driver on that path. It must not double as the fallback: a dropped
    // connection carries no user-safe text, and would otherwise be reported as a fleet-admin
    // configuration problem the driver cannot act on.
    checklistError.value = safeErrorMessage(
      reason,
      __("Could not load the inspection template. Check your connection, then try again."),
    );
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
      ? __("The vehicle receipt and the signed inspection were recorded.")
      : __("The vehicle return and the signed inspection were recorded.");
    emit("saved", result);
  } catch (reason) {
    submitError.value = safeErrorMessage(reason, __("Could not save the inspection. Your answers stayed and you can try again."));
  } finally {
    saving.value = false;
  }
}

onMounted(loadChecklist);
</script>

<template>
  <section class="salis-page salis-form-page vehicle-handover" :aria-busy="loadingChecklist">
    <header>
      <p class="salis-eyebrow">{{ __("Salis") }}</p>
      <h2>{{ title }}</h2>
      <p>{{ intro }}</p>
    </header>

    <PortalSkeleton v-if="loadingChecklist" :rows="4" :label="__('Loading the approved inspection template')" />
    <PortalErrorState
      v-else-if="checklistError"
      :title="__('Could not start the vehicle inspection')"
      :message="checklistError"
      @retry="loadChecklist"
    />
    <form v-else class="salis-form" @submit.prevent="submit">
      <section class="vehicle-handover__context">
        <div class="record-identity">
          <strong>{{ __("Approved Inspection Template") }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ checklistData.template }}</bdi>
        </div>
        <bdi v-if="checklistData.vehicle" dir="auto" translate="no">{{ checklistData.vehicle }}</bdi>
      </section>

      <FormControl v-model="form.odometer" type="number" size="lg" :label="__('Current Odometer Reading')" min="0" required />
      <FormControl
        v-model="form.fuel_level"
        type="select"
        size="lg"
        :label="__('Fuel Level')"
        :options="[
          { label: __('Select the Level'), value: '' },
          { label: __('Empty'), value: 'Empty' },
          { label: __('Quarter'), value: 'Quarter' },
          { label: __('Half'), value: 'Half' },
          { label: __('Three Quarters'), value: 'Three Quarters' },
          { label: __('Full'), value: 'Full' },
        ]"
      />

      <fieldset class="vehicle-handover__checklist">
        <legend>{{ __("Inspection Results") }}</legend>
        <article v-for="(row, index) in rows" :key="`${index}:${row.check_item}`" class="vehicle-handover__item">
          <div class="record-identity">
            <strong dir="auto">{{ row.check_item }}</strong>
            <span>{{ __("Item {0} of {1}", [index + 1, rows.length]) }}</span>
          </div>
          <div class="vehicle-handover__decisions" role="group" :aria-label="__('Result for {0}', [row.check_item])">
            <Button type="button" variant="outline" :aria-pressed="row.ok === true" @click="decide(row, true)">{{ __("OK") }}</Button>
            <Button type="button" variant="outline" :aria-pressed="row.ok === false" @click="decide(row, false)">{{ __("Not OK") }}</Button>
          </div>
          <FormControl
            v-if="row.ok === false"
            v-model="row.remark"
            type="textarea"
            :label="__('Fault Note — {0}', [row.check_item])"
            :placeholder="row.default_remark || __('Describe the unsound condition')"
            rows="2"
            required
          />
        </article>
      </fieldset>

      <FormControl v-model="form.condition_notes" type="textarea" size="lg" rows="3" :label="__('General Condition Notes')" />
      <FileUploader
        :file-types="['image/*', 'application/pdf']"
        :upload-args="{ private: 1, folder: 'Home/Attachments' }"
        @success="onUploaded"
      >
        <template #default="{ openFileSelector, uploading, error: uploadError }">
          <div class="salis-upload vehicle-handover__evidence">
            <strong>{{ __("The Signed Evidence") }} <span aria-hidden="true">*</span></strong>
            <Button type="button" variant="outline" :loading="uploading" @click="openFileSelector">
              {{ form.signed_evidence ? __("Evidence Attached") : __("Attach the Signed Evidence") }}
            </Button>
            <bdi v-if="form.signed_evidence" class="record-reference" dir="auto" translate="no">{{ form.signed_evidence }}</bdi>
            <p v-if="uploadError" class="salis-error" role="alert">{{ __("Could not upload the evidence. Try again.") }}</p>
          </div>
        </template>
      </FileUploader>

      <p v-if="notice" class="salis-notice" role="status">{{ notice }}</p>
      <p v-if="submitError" class="salis-error" role="alert">{{ submitError }}</p>
      <p v-if="submitReason" class="feature-reason">{{ submitReason }}</p>
      <Button type="submit" variant="solid" theme="green" size="lg" :loading="saving" :disabled="!canSubmit || saving">
        {{ direction === 'Receipt' ? __('Confirm Receipt') : __('Confirm Return') }}
      </Button>
    </form>
  </section>
</template>
