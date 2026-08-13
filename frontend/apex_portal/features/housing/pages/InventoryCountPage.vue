<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, LoadingIndicator, createResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { conditionLabel } from "../../../core/displayLabels.js";

const values = reactive({});
const error = ref("");
const inventory = createResource({
  url: "apex.habitat.api.housing_count.get_inventory_for_building",
  makeParams: () => ({ building: building.value }),
});
const save = createResource({ url: "apex.habitat.api.housing_count.submit_counts" });
const rows = computed(() => inventory.data?.items || []);
const conditions = computed(() => (
  inventory.data?.conditions || []
).map((value) => ({ label: conditionLabel(value), value })));

watch(building, async (value) => {
  Object.keys(values).forEach((key) => delete values[key]);
  if (value) await inventory.fetch();
}, { immediate: true });
function valueFor(row) {
  if (!values[row.name]) {
    values[row.name] = {
      name: row.name,
      counted_quantity: row.counted_quantity ?? row.expected_quantity ?? 0,
      condition: row.condition || "",
      notes: row.notes || "",
    };
  }
  return values[row.name];
}
async function submit() {
  error.value = "";
  try {
    const response = await save.submit({ building: building.value, lines: JSON.stringify(Object.values(values)) });
    if (response.failed) {
      error.value = `حُفظ ${response.saved} وتعذر حفظ ${response.failed}. راجع السطور المعلّمة.`;
    } else {
      toast.create({ type: "success", message: "تم حفظ الجرد" });
    }
    await inventory.fetch();
  } catch (exception) {
    error.value = exception.message || "تعذر حفظ الجرد.";
  }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>جرد السكن</h2><BuildingPicker /></header>
    <LoadingIndicator v-if="inventory.loading" aria-label="جارٍ تحميل الجرد" />
    <ErrorMessage v-else-if="inventory.error" message="تعذر تحميل الجرد." />
    <p v-else-if="!rows.length && building" class="feature-page__empty">لا توجد أصناف جرد لهذا المبنى.</p>
    <form v-else-if="rows.length" class="inventory-form" @submit.prevent="submit">
      <article v-for="row in rows" :key="row.name" class="feature-card inventory-row">
        <div><strong dir="auto">{{ row.item_label || row.item_name }}</strong><small>{{ row.room_label || 'المبنى' }} · المتوقع {{ row.expected_quantity }}</small></div>
        <FormControl v-model="valueFor(row).counted_quantity" type="number" label="العدد الفعلي" min="0" required />
        <FormControl v-model="valueFor(row).condition" type="select" label="الحالة" :options="conditions" />
        <FormControl v-model="valueFor(row).notes" class="inventory-row__notes" type="textarea" label="ملاحظة" :rows="2" />
      </article>
      <ErrorMessage v-if="error" :message="error" />
      <Button type="submit" theme="green" variant="solid" :loading="save.loading">حفظ الجرد</Button>
    </form>
  </section>
</template>
