<script setup>
import { createResource } from "frappe-ui";
import SimpleListPage from "../components/SimpleListPage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_incidents",
  method: "GET",
  auto: false,
});
</script>
<template>
  <SimpleListPage :title="__('Incidents')" :resource="resource" :empty="__('No incidents are recorded on your vehicle.')" create-to="/incidents/new" />
</template>
