<script setup>
import { createListResource } from "frappe-ui";
import ResourceListPage from "../components/ResourceListPage.vue";
import { maintenanceIssueLabel, statusLabel } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";
const requests = createListResource({
  doctype: "Maintenance Request",
  fields: ["name", "issue_type", "issue_description", "status", "building", "room", "priority"],
  orderBy: "modified desc",
  pageLength: 50,
  auto: true,
});
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canCreate = capabilities.includes("maintenance_create");
</script>
<template>
  <ResourceListPage :title="__('Maintenance Requests')" :rows="requests.data || []" :loading="requests.list.loading" :error="requests.list.error" :refresh="requests.fetch">
    <template #actions>
      <RouterLink v-if="canCreate" class="supervisor-primary-link" to="/maintenance/new">
        {{ __("New Maintenance Request") }}
      </RouterLink>
    </template>
    <template #row="{ row }">
      <RouterLink :to="`/maintenance/${row.name}`">
        <strong>{{ maintenanceIssueLabel(row.issue_type) || __("Maintenance Request") }}</strong>
      </RouterLink>
      <span><bdi dir="auto">{{ row.building }}</bdi> · <bdi dir="auto" translate="no">{{ row.room }}</bdi></span>
      <small>{{ statusLabel(row.status) }} · {{ statusLabel(row.priority) }}</small>
    </template>
  </ResourceListPage>
</template>
