<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.submit_additional_fuel_request",
  method: "POST",
  auto: false,
});
const fields = [
  { name: "topup_litres", type: "number", label: __("Requested Increase in Litres"), required: true },
  { name: "reason", type: "textarea", rows: 4, label: __("Reason for the Increase"), required: true },
];
</script>
<template>
  <ActionForm :title="__('Additional Fuel Request')" :intro="__('The request goes to the supervisor; the balance is not added before approval.')" :fields="fields" :resource="resource" action-key="additional-fuel" />
</template>
