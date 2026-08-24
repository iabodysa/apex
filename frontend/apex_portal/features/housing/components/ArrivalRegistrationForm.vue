<script setup>
import { computed, reactive, watch } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import { arrivalRegistrationParams } from "../arrivalFlow.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({
  manifest: { type: Object, default: null },
  building: { type: String, required: true },
});
const emit = defineEmits(["cancel", "registered", "error"]);

const register = createResource({ url: "apex.habitat.api.arrivals_desk.register_temporary_worker" });
const form = reactive({ worker_name: "", passport_number: "", nationality: "", cell_number: "" });

// The picked manifest row seeds the identity fields in a pre-flush watcher, so the template only
// reads them. A cleared manifest keeps whatever the clerk already typed.
watch(() => props.manifest, (row) => {
  if (!row) return;
  form.worker_name = row.worker_name || "";
  form.passport_number = row.passport_number || "";
  form.nationality = row.nationality || "";
}, { immediate: true });

// `required` on the fields never fires while the submit button is disabled, so the clerk gets no
// native prompt either. This says which field is still holding the registration.
const blockedReason = computed(() => {
  if (!form.worker_name) return __("Type the worker's name to enable registration.");
  if (!form.passport_number) return __("Type the passport number to enable registration.");
  return "";
});

async function addTemporary() {
  emit("error", "");
  try {
    const result = await register.submit(
      arrivalRegistrationParams(form, props.manifest, props.building),
    );
    Object.assign(form, { worker_name: "", passport_number: "", nationality: "", cell_number: "" });
    emit("registered", result);
  } catch (reason) {
    emit("error", safeErrorMessage(reason, __("Could not register the worker.")));
  }
}
</script>

<template>
  <form class="arrival-panel arrival-form" @submit.prevent="addTemporary">
    <div class="arrival-panel__title"><h3>{{ manifest ? __("Register {0}", [manifest.worker_name]) : __("Add a worker not in the list") }}</h3><Button v-if="manifest" type="button" variant="ghost" @click="$emit('cancel')">{{ __("Cancel") }}</Button></div>
    <div class="arrival-form__grid">
      <FormControl v-model="form.worker_name" :label="__('Worker Name')" required />
      <FormControl v-model="form.passport_number" :label="__('Passport Number')" required />
      <FormControl v-model="form.nationality" :label="__('Nationality')" />
      <FormControl v-model="form.cell_number" :label="__('Mobile Number')" />
    </div>
    <p v-if="blockedReason" class="feature-state">{{ blockedReason }}</p>
    <Button type="submit" theme="green" variant="solid" :loading="register.loading" :disabled="!form.worker_name || !form.passport_number">{{ __("Register Worker") }}</Button>
  </form>
</template>
