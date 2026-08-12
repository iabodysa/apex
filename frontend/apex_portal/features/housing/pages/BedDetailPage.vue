<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, FormControl, LoadingIndicator, createResource, toast } from "frappe-ui";

const route = useRoute();
const error = ref("");
const checkInForm = reactive({ party_type: "Employee", party: "", project: "" });
const bed = createResource({ url: "frappe.client.get", makeParams: () => ({ doctype: "Bed", name: route.params.bed }) });
const checkIn = createResource({ url: "apex.habitat.api.front_desk.quick_check_in" });
const checkOut = createResource({ url: "apex.habitat.api.front_desk.quick_check_out" });
const occupied = computed(() => bed.data?.status === "Occupied");
onMounted(() => bed.fetch());
async function arrive() {
  error.value = "";
  try {
    await checkIn.submit({ bed: route.params.bed, ...checkInForm });
    toast.create({ type: "success", message: "تم تسكين العامل" });
    Object.assign(checkInForm, { party_type: "Employee", party: "", project: "" });
    await bed.fetch();
  } catch (exception) { error.value = exception.message || "تعذر التسكين."; }
}
async function depart() {
  error.value = "";
  try {
    const response = await checkOut.submit({ bed: route.params.bed, checkout_reason: "End of Contract" });
    if (response?.requires_full_form) {
      error.value = "يجب استلام عهد العامل قبل إتمام المغادرة.";
      return;
    }
    toast.create({ type: "success", message: "تم تسجيل المغادرة" });
    await bed.fetch();
  } catch (exception) { error.value = exception.message || "تعذر تسجيل المغادرة."; }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل السرير</h2>
    <LoadingIndicator v-if="bed.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="bed.error" message="تعذر تحميل السرير." />
    <template v-else-if="bed.data">
      <article class="feature-card"><strong>{{ bed.data.bed_code || bed.data.name }}</strong><span>{{ bed.data.room }}</span><small>{{ bed.data.status }} · {{ bed.data.condition }}</small></article>
      <form v-if="!occupied" class="feature-form" @submit.prevent="arrive">
        <FormControl v-model="checkInForm.party_type" type="select" label="نوع الساكن" :options="[{ label: 'موظف', value: 'Employee' }, { label: 'عامل مؤقت', value: 'Temporary Worker' }]" />
        <FormControl v-model="checkInForm.party" label="رقم الساكن" required />
        <FormControl v-model="checkInForm.project" label="المشروع" />
        <Button type="submit" variant="solid" :loading="checkIn.loading">تسكين</Button>
      </form>
      <Button v-else variant="solid" :loading="checkOut.loading" @click="depart">تسجيل المغادرة</Button>
      <RouterLink v-if="error.includes('العهد')" to="/custody">الانتقال إلى العهد</RouterLink>
      <ErrorMessage v-if="error" :message="error" />
    </template>
  </section>
</template>
