<script setup>
import { computed } from "vue";
import BuildingPicker from "../components/BuildingPicker.vue";
import ResourceListPage from "../components/ResourceListPage.vue";
import { building } from "../building.js";
const params = computed(() => ({ building: building.value }));
</script>
<template>
  <BuildingPicker />
  <nav class="feature-actions" aria-label="إجراءات اليوم">
    <RouterLink to="/beds">تسكين أو مغادرة</RouterLink>
    <RouterLink to="/arrivals">القادمون اليوم</RouterLink>
    <RouterLink to="/maintenance/new">طلب صيانة</RouterLink>
  </nav>
  <ResourceListPage v-if="building" title="مهام اليوم" endpoint="apex.habitat.api.front_desk.building_open_requests" :params="params">
    <template #row="{ row }">
      <strong>{{ row.open_requests }}</strong>
      <span>طلباً مفتوحاً من السكان</span>
      <small>الحالات: {{ row.statuses.join('، ') }}</small>
    </template>
  </ResourceListPage>
</template>
