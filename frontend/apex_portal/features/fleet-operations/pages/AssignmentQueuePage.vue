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
  <!-- TODO(A-532): the only QueuePage without detail-base, so its rows open nothing -->
  <QueuePage title="قائمة الإسناد" :resource="resource" empty="لا توجد عمليات إسناد تحتاج متابعة." />
</template>
