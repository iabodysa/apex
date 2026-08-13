<script setup>
import { createResource } from "frappe-ui";
import SimpleListPage from "../components/SimpleListPage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_complaints",
  method: "GET",
  auto: false,
});
</script>
<template>
  <SimpleListPage title="البلاغات والشكاوى" :resource="resource" empty="لا توجد بلاغات مفتوحة أو سابقة." create-to="/complaints/new" />
</template>
