<script setup>
import { createResource } from "frappe-ui";
import SimpleListPage from "../components/SimpleListPage.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_complaints",
  method: "GET",
  auto: false,
});
</script>
<template>
  <SimpleListPage :title="__('Complaints')" :resource="resource" :empty="__('No open or past complaints.')" create-to="/complaints/new" />
</template>
