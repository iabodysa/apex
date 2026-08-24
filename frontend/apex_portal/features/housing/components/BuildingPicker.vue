<script setup>
import { computed, onMounted, watch } from "vue";
import { Button, Select } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { building, selectBuilding } from "../building.js";
import { createSupervisorBuildingsResource } from "../data/buildings.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({ resource: { type: Object, default: null } });
const buildings = props.resource || createSupervisorBuildingsResource();
// The parent that already reads the portfolio owns the request; this picker only reads it.
const ownsRequest = !props.resource;
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
    <PortalSkeleton v-if="buildings.loading" :rows="1" :label="__('Loading Buildings')" />
    <div v-else-if="buildings.error" class="feature-state feature-state--error">
      <p>{{ __("Could not load the buildings.") }}</p>
      <Button variant="outline" :label="__('Retry')" @click="load" />
    </div>
    <div v-else-if="!options.length" class="feature-state">{{ __("No buildings available.") }}</div>
    <Select v-else :model-value="building" :options="options" :placeholder="__('Choose the Building')" :aria-label="__('Building')" @update:model-value="selectBuilding" />
  </template>
</template>
