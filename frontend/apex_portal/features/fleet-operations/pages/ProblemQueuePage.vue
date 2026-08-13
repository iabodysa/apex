<script setup>
import { createResource } from "frappe-ui";
import QueuePage from "../components/QueuePage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_os.get_problem_queue",
  method: "GET",
  auto: false,
});
</script>
<template>
  <QueuePage title="المشكلات والبلاغات" :resource="resource" detail-base="/problems" empty="لا توجد مشكلات ضمن مشاريعك." />
</template>
