<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.receive_vehicle",
  method: "POST",
  auto: false,
});
const fields = [
  { name: "odometer", type: "number", label: "قراءة العداد", required: true },
  {
    name: "fuel_level",
    type: "select",
    label: "مستوى الوقود",
    options: [
      { label: "فارغ", value: "Empty" },
      { label: "ربع", value: "Quarter" },
      { label: "نصف", value: "Half" },
      { label: "ثلاثة أرباع", value: "Three Quarters" },
      { label: "ممتلئ", value: "Full" },
    ],
  },
  { name: "condition_notes", type: "textarea", rows: 3, label: "ملاحظات الحالة" },
  { name: "signed_evidence", type: "file", label: "إثبات الاستلام" },
];
</script>
<template>
  <ActionForm title="استلام المركبة" intro="راجع المركبة وسجل القراءة الفعلية قبل التأكيد." :fields="fields" :resource="resource" action-key="vehicle-receipt" />
</template>
