<script setup>
import { createResource } from "frappe-ui";
import SimpleListPage from "../components/SimpleListPage.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_incidents",
  method: "GET",
  auto: false,
});
</script>
<template>
  <SimpleListPage title="الحوادث" :resource="resource" empty="لا توجد حوادث مسجلة على مركبتك." create-to="/incidents/new" />
</template>
