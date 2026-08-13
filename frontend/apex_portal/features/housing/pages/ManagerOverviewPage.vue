<script setup>
import { onMounted } from "vue";
import ResourceListPage from "../components/ResourceListPage.vue";
import { createSupervisorBuildingsResource } from "../data/buildings.js";

const buildings = createSupervisorBuildingsResource();
onMounted(() => buildings.fetch());
</script>
<template>
  <ResourceListPage title="نظرة عامة على السكن" :rows="buildings.data || []" :loading="buildings.loading" :error="buildings.error" :refresh="buildings.fetch" empty-text="لا توجد مبانٍ نشطة.">
    <template #row="{ row }">
      <RouterLink to="/beds">
        <strong dir="auto">{{ row.building_title }}</strong>
      </RouterLink>
      <span>{{ row.occupied }} مشغول · {{ row.available }} متاح · {{ row.blocked + row.oos }} غير جاهز</span>
      <small>نسبة الإشغال {{ row.occupancy_pct }}٪</small>
    </template>
  </ResourceListPage>
</template>
