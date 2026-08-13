<script setup>
import { createListResource } from "frappe-ui";
import ResourceListPage from "../components/ResourceListPage.vue";
import { statusLabel } from "../../../core/displayLabels.js";
const requests = createListResource({
  doctype: "Maintenance Request",
  fields: ["name", "issue_type", "issue_description", "status", "building", "room", "priority"],
  orderBy: "modified desc",
  pageLength: 50,
  auto: true,
});
</script>
<template>
  <ResourceListPage title="طلبات الصيانة" :rows="requests.data || []" :loading="requests.list.loading" :error="requests.list.error" :refresh="requests.fetch">
    <template #row="{ row }">
      <RouterLink :to="`/maintenance/${row.name}`">
        <strong>{{ row.issue_type }}</strong>
      </RouterLink>
      <span>{{ row.building }} · {{ row.room }}</span>
      <small>{{ statusLabel(row.status) }} · {{ statusLabel(row.priority) }}</small>
    </template>
  </ResourceListPage>
</template>
