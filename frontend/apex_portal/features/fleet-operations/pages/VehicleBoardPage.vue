<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_fleet_os",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="المركبات" :resource="resource" rows-key="vehicles" detail-base="/vehicles" empty="لا توجد مركبات ضمن المشاريع المسموحة." />
</template>
