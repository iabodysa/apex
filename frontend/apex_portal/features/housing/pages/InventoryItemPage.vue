<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, FormControl, LoadingIndicator, createDocumentResource, createResource, toast } from "frappe-ui";

const route = useRoute();
const form = reactive({ counted_quantity: 0, condition: "", notes: "" });
const error = ref("");
const item = createDocumentResource({
  doctype: "Housing Inventory",
  name: route.params.item,
  auto: false,
});
const save = createResource({ url: "apex.habitat.api.housing_count.submit_counts" });
onMounted(async () => {
  await item.reload();
  Object.assign(form, {
    counted_quantity: item.doc?.counted_quantity ?? item.doc?.expected_quantity ?? 0,
    condition: item.doc?.condition || "",
    notes: item.doc?.notes || "",
  });
});
async function submit() {
  error.value = "";
  try {
    const response = await save.submit({
      building: item.doc.building,
      lines: JSON.stringify([{ name: item.doc.name, ...form }]),
    });
    if (response.failed) throw new Error(response.errors?.[0]?.message || "تعذر حفظ الصنف.");
    toast.create({ type: "success", message: "تم حفظ نتيجة الجرد" });
    await item.reload();
  } catch (exception) {
    error.value = exception.message || "تعذر حفظ نتيجة الجرد.";
  }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل الجرد</h2>
    <LoadingIndicator v-if="item.get.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="item.get.error" message="تعذر تحميل الصنف." />
    <form v-else-if="item.doc" class="feature-card feature-form" @submit.prevent="submit">
      <strong dir="auto">{{ item.doc.item_name }}</strong>
      <span>{{ item.doc.room }} · المتوقع {{ item.doc.expected_quantity }}</span>
      <FormControl v-model="form.counted_quantity" type="number" min="0" label="العدد الفعلي" required />
      <FormControl v-model="form.condition" label="الحالة" />
      <FormControl v-model="form.notes" label="ملاحظة" />
      <ErrorMessage v-if="error" :message="error" />
      <Button type="submit" theme="green" variant="solid" :loading="save.loading">حفظ</Button>
    </form>
  </section>
</template>
