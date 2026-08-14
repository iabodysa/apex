<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_handover_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="قائمة الاستلام" :resource="resource" detail-base="/handovers" empty="لا توجد مستندات استلام معلقة." />
</template>
