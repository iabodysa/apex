<script setup>
import { createListResource } from "frappe-ui";
import ResourceListPage from "../components/ResourceListPage.vue";
import { statusLabel } from "../../../core/displayLabels.js";
const deliveries = createListResource({
  doctype: "Facility Asset Delivery",
  fields: [
    "name", "status", "facility_asset", "facility_asset.asset_name as asset_name",
    "asset_serial_number", "from_building", "to_building", "delivery_date",
  ],
  orderBy: "modified desc",
  pageLength: 50,
  auto: true,
});
</script>
<template>
  <ResourceListPage title="تسليم الأصول" :rows="deliveries.data || []" :loading="deliveries.list.loading" :error="deliveries.list.error" :refresh="deliveries.fetch">
    <template #row="{ row }">
      <RouterLink :to="`/delivery/${row.name}`">
        <div class="record-identity">
          <strong dir="auto">{{ row.asset_name || "أصل سكني" }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ row.asset_serial_number || row.facility_asset }}</bdi>
        </div>
      </RouterLink>
      <span>{{ row.from_building }} ← {{ row.to_building }}</span>
      <small>{{ statusLabel(row.status) }}</small>
    </template>
  </ResourceListPage>
</template>
