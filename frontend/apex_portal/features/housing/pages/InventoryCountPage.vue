<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { conditionLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const values = reactive({});
const error = ref("");
const inventory = createResource({
  url: "apex.habitat.api.housing_count.get_inventory_for_building",
  makeParams: () => ({ building: building.value }),
});
const save = createResource({ url: "apex.habitat.api.housing_count.submit_counts" });
// Tied to the selected building so a cleared picker cannot leave the previous building's rows
// on screen without their seeded draft entries.
const rows = computed(() => (building.value && inventory.data?.items) || []);
const conditions = computed(() => (
  inventory.data?.conditions || []
).map((value) => ({ label: conditionLabel(value), value })));

watch(building, async (value) => {
  Object.keys(values).forEach((key) => delete values[key]);
  if (value) await inventory.fetch();
}, { immediate: true });
// The draft entry for a row is seeded here, never from the template: a pre-flush watcher runs
// before the render that first shows the row, so rendering only ever reads.
watch(rows, (list) => {
  for (const row of list) {
    if (values[row.name]) continue;
    values[row.name] = {
      name: row.name,
      counted_quantity: row.counted_quantity ?? row.expected_quantity ?? 0,
      condition: row.condition || "",
      notes: row.notes || "",
    };
  }
}, { immediate: true });
async function submit() {
  error.value = "";
  try {
    const response = await save.submit({ building: building.value, lines: JSON.stringify(Object.values(values)) });
    if (response.failed) {
      error.value = __("Saved {0} and failed to save {1}. Check the flagged rows.", [response.saved, response.failed]);
    } else {
      toast.create({ type: "success", message: __("The inventory was saved") });
    }
    await inventory.fetch();
  } catch (exception) {
    error.value = safeErrorMessage(exception, __("Could not save the inventory."));
  }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>{{ __("Housing Inventory") }}</h2><BuildingPicker /></header>
    <PortalSkeleton v-if="inventory.loading" :rows="3" :label="__('Loading Inventory')" />
    <PortalErrorState v-else-if="inventory.error" :title="__('Could not load the inventory')" :message="inventory.error" @retry="inventory.fetch()" />
    <p v-else-if="!rows.length && building" class="feature-page__empty">{{ __("No inventory items for this building.") }}</p>
    <form v-else-if="rows.length" class="inventory-form" @submit.prevent="submit">
      <article v-for="row in rows" :key="row.name" class="feature-card inventory-row">
        <div><strong dir="auto">{{ row.item_label || row.item_name }}</strong><small>{{ row.room_label || __("Building") }} · {{ __("Expected {0}", [row.expected_quantity]) }}</small></div>
        <FormControl v-model="values[row.name].counted_quantity" type="number" :label="__('Actual Count')" min="0" required />
        <FormControl v-model="values[row.name].condition" type="select" :label="__('Status')" :options="conditions" />
        <FormControl v-model="values[row.name].notes" class="inventory-row__notes" type="textarea" :label="__('Remark')" :rows="2" />
      </article>
      <ErrorMessage v-if="error" :message="error" />
      <Button type="submit" theme="green" variant="solid" :loading="save.loading">{{ __("Save Inventory") }}</Button>
    </form>
  </section>
</template>
