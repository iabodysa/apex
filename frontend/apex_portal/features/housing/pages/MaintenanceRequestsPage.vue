<script setup>
import ResourceListPage from "../components/ResourceListPage.vue";
const params = { doctype: "Maintenance Request", fields: ["name", "issue_type", "issue_description", "status", "building", "room", "priority"], limit_page_length: 50, order_by: "modified desc" };
</script>
<template>
  <ResourceListPage title="طلبات الصيانة" endpoint="frappe.client.get_list" :params="params">
    <template #row="{ row }">
      <RouterLink :to="`/maintenance/${row.name}`"><strong>{{ row.issue_type }}</strong></RouterLink>
      <span>{{ row.building }} · {{ row.room }}</span>
      <small>{{ row.status }} · {{ row.priority }}</small>
    </template>
  </ResourceListPage>
</template>
