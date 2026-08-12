<script setup>
import ResourceListPage from "../components/ResourceListPage.vue";
</script>
<template>
  <ResourceListPage title="نظرة عامة على السكن" endpoint="apex.habitat.api.front_desk.list_supervisor_buildings" empty-text="لا توجد مبانٍ نشطة.">
    <template #row="{ row }">
      <RouterLink to="/beds"><strong dir="auto">{{ row.building_title }}</strong></RouterLink>
      <span>{{ row.occupied }} مشغول · {{ row.available }} متاح · {{ row.blocked + row.oos }} غير جاهز</span>
      <small>نسبة الإشغال {{ row.occupancy_pct }}٪</small>
    </template>
  </ResourceListPage>
</template>
