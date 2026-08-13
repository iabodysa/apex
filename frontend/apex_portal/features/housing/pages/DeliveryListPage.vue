<script setup>
import ResourceListPage from "../components/ResourceListPage.vue";
import { statusLabel } from "../../../core/displayLabels.js";
const params = { doctype: "Facility Asset Delivery", fields: ["name", "status", "facility_asset", "from_building", "to_building", "delivery_date"], limit_page_length: 50, order_by: "modified desc" };
</script>
<template>
  <ResourceListPage title="تسليم الأصول" endpoint="frappe.client.get_list" :params="params">
    <template #row="{ row }">
      <RouterLink :to="`/delivery/${row.name}`"><strong dir="auto">{{ row.facility_asset }}</strong></RouterLink>
      <span>{{ row.from_building }} ← {{ row.to_building }}</span>
      <small>{{ statusLabel(row.status) }}</small>
    </template>
  </ResourceListPage>
</template>
