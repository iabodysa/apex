<script setup>
import { computed, onMounted, watch } from "vue";
import { Button, Select } from "frappe-ui";
import { building, selectBuilding } from "../building.js";
import { createSupervisorBuildingsResource } from "../data/buildings.js";

const props = defineProps({ resource: { type: Object, default: null } });
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canSelectBuilding = capabilities.includes("estate_read") || capabilities.includes("check_in");
const buildings = props.resource || (canSelectBuilding ? createSupervisorBuildingsResource() : null);
// The parent that already reads the portfolio owns the request; this picker only reads it.
const ownsRequest = Boolean(buildings) && !props.resource;
const options = computed(() =>
  (buildings?.data || []).map((row) => ({
    label: row.building_title || row.building,
    value: row.building,
  })),
);
function selectFirst() {
  if (!building.value && options.value.length) selectBuilding(options.value[0].value);
}
async function load() {
  if (!buildings) return;
  try {
    await buildings.fetch();
  } catch {
    return;
  }
  selectFirst();
}
watch(options, selectFirst, { immediate: true });
onMounted(() => {
  if (ownsRequest) load();
});
</script>

<template>
  <template v-if="buildings">
    <div v-if="buildings.loading" class="feature-state" role="status">جاري تحميل المباني…</div>
    <div v-else-if="buildings.error" class="feature-state feature-state--error">
      <p>تعذر تحميل المباني.</p>
      <Button variant="outline" label="إعادة المحاولة" @click="load" />
    </div>
    <div v-else-if="!options.length" class="feature-state">لا توجد مبانٍ متاحة.</div>
    <Select v-else :model-value="building" :options="options" placeholder="اختر المبنى" aria-label="المبنى" @update:model-value="selectBuilding" />
  </template>
</template>
