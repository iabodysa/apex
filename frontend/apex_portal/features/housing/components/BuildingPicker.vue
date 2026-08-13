<script setup>
import { computed, onMounted } from "vue";
import { Button, Select, createResource } from "frappe-ui";
import { building, selectBuilding } from "../building.js";

const buildings = createResource({ url: "apex.habitat.api.front_desk.list_supervisor_buildings" });
const options = computed(() => (buildings.data || []).map((row) => ({
  label: row.building_title || row.building,
  value: row.building,
})));
async function load() {
  try {
    await buildings.fetch();
  } catch {
    return;
  }
  if (!building.value && options.value.length) selectBuilding(options.value[0].value);
}
onMounted(load);
</script>

<template>
  <div v-if="buildings.loading" class="feature-state" role="status">جاري تحميل المباني…</div>
  <div v-else-if="buildings.error" class="feature-state feature-state--error">
    <p>تعذر تحميل المباني.</p>
    <Button variant="outline" label="إعادة المحاولة" @click="load" />
  </div>
  <div v-else-if="!options.length" class="feature-state">لا توجد مبانٍ متاحة.</div>
  <Select
    v-else
    :model-value="building"
    :options="options"
    placeholder="اختر المبنى"
    aria-label="المبنى"
    @update:model-value="selectBuilding"
  />
</template>
