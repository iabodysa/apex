<script setup>
import { computed, onMounted } from "vue";
import { Select, createResource } from "frappe-ui";
import { building, selectBuilding } from "../building.js";

const buildings = createResource({ url: "apex.habitat.api.front_desk.list_supervisor_buildings" });
const options = computed(() => (buildings.data || []).map((row) => ({
  label: row.building_title || row.building,
  value: row.building,
})));
onMounted(async () => {
  await buildings.fetch();
  if (!building.value && options.value.length) selectBuilding(options.value[0].value);
});
</script>

<template>
  <Select
    :model-value="building"
    :options="options"
    placeholder="اختر المبنى"
    aria-label="المبنى"
    @update:model-value="selectBuilding"
  />
</template>
