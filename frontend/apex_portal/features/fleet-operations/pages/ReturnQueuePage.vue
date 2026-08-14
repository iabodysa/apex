<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_return_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="قائمة الإرجاع" :resource="resource" detail-base="/returns" empty="لا توجد مركبات بانتظار الإرجاع." />
</template>
