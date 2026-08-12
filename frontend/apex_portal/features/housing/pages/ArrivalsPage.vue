<script setup>
import { computed } from "vue";
import BuildingPicker from "../components/BuildingPicker.vue";
import ResourceListPage from "../components/ResourceListPage.vue";
import { building } from "../building.js";
const params = computed(() => ({ building: building.value }));
</script>
<template>
  <BuildingPicker />
  <ResourceListPage v-if="building" title="القادمون اليوم" endpoint="apex.habitat.api.arrivals_desk.get_expected_arrivals" :params="params" rows-key="workers">
    <template #row="{ row }">
      <strong dir="auto">{{ row.worker_name }}</strong>
      <span>{{ row.labour_supplier || row.project || 'بدون جهة محددة' }}</span>
      <small>{{ row.arrived ? 'وصل وسُجّل' : 'بانتظار الوصول' }}</small>
    </template>
  </ResourceListPage>
</template>
