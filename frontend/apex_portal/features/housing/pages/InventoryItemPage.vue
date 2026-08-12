<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, FormControl, LoadingIndicator, createResource, toast } from "frappe-ui";

const route = useRoute();
const form = reactive({ counted_quantity: 0, condition: "", notes: "" });
const error = ref("");
const item = createResource({ url: "frappe.client.get", makeParams: () => ({ doctype: "Housing Inventory", name: route.params.item }) });
const save = createResource({ url: "apex.habitat.api.housing_count.submit_counts" });
onMounted(async () => {
  await item.fetch();
  Object.assign(form, {
    counted_quantity: item.data?.counted_quantity ?? item.data?.expected_quantity ?? 0,
    condition: item.data?.condition || "",
    notes: item.data?.notes || "",
  });
});
async function submit() {
  error.value = "";
  try {
    const response = await save.submit({
      building: item.data.building,
      lines: JSON.stringify([{ name: item.data.name, ...form }]),
    });
    if (response.failed) throw new Error(response.errors?.[0]?.message || "تعذر حفظ الصنف.");
    toast.create({ type: "success", message: "تم حفظ نتيجة الجرد" });
    await item.fetch();
  } catch (exception) { error.value = exception.message || "تعذر حفظ نتيجة الجرد."; }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل الجرد</h2>
    <LoadingIndicator v-if="item.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="item.error" message="تعذر تحميل الصنف." />
    <form v-else-if="item.data" class="feature-card feature-form" @submit.prevent="submit">
      <strong dir="auto">{{ item.data.item_name }}</strong>
      <span>{{ item.data.room }} · المتوقع {{ item.data.expected_quantity }}</span>
      <FormControl v-model="form.counted_quantity" type="number" min="0" label="العدد الفعلي" required />
      <FormControl v-model="form.condition" label="الحالة" />
      <FormControl v-model="form.notes" label="ملاحظة" />
      <ErrorMessage v-if="error" :message="error" />
      <Button type="submit" variant="solid" :loading="save.loading">حفظ</Button>
    </form>
  </section>
</template>
