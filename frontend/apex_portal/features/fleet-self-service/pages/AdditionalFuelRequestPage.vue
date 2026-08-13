<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.submit_additional_fuel_request",
  method: "POST",
  auto: false,
});
const fields = [
  { name: "topup_litres", type: "number", label: "الزيادة المطلوبة باللتر", required: true },
  { name: "reason", type: "textarea", rows: 4, label: "سبب الزيادة", required: true },
];
</script>
<template>
  <ActionForm title="طلب زيادة وقود" intro="يرسل الطلب للمشرف، ولا يضاف الرصيد قبل الاعتماد." :fields="fields" :resource="resource" action-key="additional-fuel" />
</template>
