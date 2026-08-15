<script setup>
import { computed, reactive, watch } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import { arrivalRegistrationParams } from "../arrivalFlow.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";

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
  if (!form.worker_name) return "اكتب اسم العامل لتفعيل التسجيل.";
  if (!form.passport_number) return "اكتب رقم الجواز لتفعيل التسجيل.";
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
    emit("error", safeErrorMessage(reason, "تعذّر تسجيل العامل."));
  }
}
</script>

<template>
  <form class="arrival-panel arrival-form" @submit.prevent="addTemporary">
    <div class="arrival-panel__title"><h3>{{ manifest ? `تسجيل ${manifest.worker_name}` : 'إضافة عامل غير موجود في القائمة' }}</h3><Button v-if="manifest" type="button" variant="ghost" @click="$emit('cancel')">إلغاء</Button></div>
    <div class="arrival-form__grid">
      <FormControl v-model="form.worker_name" label="اسم العامل" required />
      <FormControl v-model="form.passport_number" label="رقم الجواز" required />
      <FormControl v-model="form.nationality" label="الجنسية" />
      <FormControl v-model="form.cell_number" label="رقم الجوال" />
    </div>
    <p v-if="blockedReason" class="feature-state">{{ blockedReason }}</p>
    <Button type="submit" theme="green" variant="solid" :loading="register.loading" :disabled="!form.worker_name || !form.passport_number">تسجيل العامل</Button>
  </form>
</template>
