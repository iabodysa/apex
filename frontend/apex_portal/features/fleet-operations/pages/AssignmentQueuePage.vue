<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_assignment_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="قائمة الإسناد" :resource="resource" empty="لا توجد عمليات إسناد تحتاج متابعة." />
</template>
