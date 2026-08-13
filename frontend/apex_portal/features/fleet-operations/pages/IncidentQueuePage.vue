<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_incident_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="الحوادث" :resource="resource" detail-base="/incidents" empty="لا توجد حوادث ضمن مشاريعك." />
</template>
