<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.submit_fuel_request",
  method: "POST",
  auto: false,
});
const fields = [
  { name: "litres", type: "number", label: "الكمية باللتر", required: true },
  { name: "station", label: "محطة الوقود" },
  { name: "notes", type: "textarea", rows: 3, label: "ملاحظة" },
];
</script>
<template>
  <ActionForm title="طلب وقود" intro="الطلب العادي مرتبط بحصتك الشهرية الحالية." :fields="fields" :resource="resource" action-key="standard-fuel" />
</template>
