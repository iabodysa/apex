<script setup>
import { computed, reactive, ref } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import { Link } from "frappe-ui/frappe";
import { safeErrorMessage } from "../../../core/errorMessage.js";

const form = reactive({ source_bed: "", target_bed: "", reason: "" });
const error = ref("");
const transfer = createResource({ url: "apex.habitat.api.transfer_board.transfer_occupant" });
// Link marks its label required but enforces nothing, so both beds are checked here.
const canSubmit = computed(() => Boolean(form.source_bed && form.target_bed));
async function submit() {
  error.value = "";
  if (!canSubmit.value) return;
  try {
    await transfer.submit({ ...form });
    toast.create({ type: "success", message: "تم نقل الساكن" });
    Object.assign(form, { source_bed: "", target_bed: "", reason: "" });
  } catch (exception) {
    error.value = safeErrorMessage(exception, "تعذر تنفيذ النقل.");
  }
}
</script>
<template>
  <section class="feature-page"><h2>نقل الساكن</h2><form class="feature-form" @submit.prevent="submit">
    <Link v-model="form.source_bed" doctype="Bed" label="السرير الحالي" placeholder="ابحث عن السرير الحالي" required />
    <Link v-model="form.target_bed" doctype="Bed" label="السرير الجديد" placeholder="ابحث عن السرير الجديد" required />
    <FormControl v-model="form.reason" type="textarea" label="سبب النقل" />
    <ErrorMessage v-if="error" :message="error" />
    <Button type="submit" theme="green" variant="solid" :disabled="!canSubmit" :loading="transfer.loading">تنفيذ النقل</Button>
  </form></section>
</template>
