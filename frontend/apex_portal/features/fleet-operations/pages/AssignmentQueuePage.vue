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
  <!-- No /assignments/:name route exists, so QueuePage renders these rows inert rather
       than as links to nowhere. Give it a detail-base the day that route ships. -->
  <QueuePage title="قائمة الإسناد" :resource="resource" empty="لا توجد عمليات إسناد تحتاج متابعة." />
</template>
