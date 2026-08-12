<script setup>
import { reactive, ref } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";

const form = reactive({ source_bed: "", target_bed: "", reason: "" });
const error = ref("");
const transfer = createResource({ url: "apex.habitat.api.transfer_board.transfer_occupant" });
async function submit() {
  error.value = "";
  try {
    await transfer.submit({ ...form });
    toast({ title: "تم نقل الساكن", icon: "check" });
    Object.assign(form, { source_bed: "", target_bed: "", reason: "" });
  } catch (exception) {
    error.value = exception.message || "تعذر تنفيذ النقل.";
  }
}
</script>
<template>
  <section class="feature-page"><h2>نقل الساكن</h2><form class="feature-form" @submit.prevent="submit">
    <FormControl v-model="form.source_bed" label="السرير الحالي" required />
    <FormControl v-model="form.target_bed" label="السرير الجديد" required />
    <FormControl v-model="form.reason" type="textarea" label="سبب النقل" />
    <ErrorMessage v-if="error" :message="error" />
    <Button type="submit" variant="solid" :loading="transfer.loading">تنفيذ النقل</Button>
  </form></section>
</template>
