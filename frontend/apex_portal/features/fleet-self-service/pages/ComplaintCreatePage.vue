<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.create_complaint",
  method: "POST",
  auto: false,
});
const fields = [
  {
    name: "priority",
    type: "select",
    label: "الأولوية",
    options: [
      { label: "منخفضة", value: "Low" },
      { label: "متوسطة", value: "Medium" },
      { label: "عالية", value: "High" },
      { label: "عاجلة", value: "Urgent" },
    ],
    default: "Medium",
  },
  { name: "subject", label: "عنوان البلاغ", required: true },
  { name: "description", type: "textarea", rows: 5, label: "التفاصيل", required: true },
  { name: "attachment", type: "file", label: "مرفق" },
];
</script>
<template>
  <ActionForm title="بلاغ جديد" intro="يصل البلاغ إلى فريق التشغيل وتظهر الردود في نفس السجل." :fields="fields" :resource="resource" action-key="complaint" />
</template>
