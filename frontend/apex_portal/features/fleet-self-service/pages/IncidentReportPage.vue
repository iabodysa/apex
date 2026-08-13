<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.report_incident",
  method: "POST",
  auto: false,
});
const fields = [
  {
    name: "incident_type",
    type: "select",
    label: "نوع الحادث",
    options: [
      { label: "حادث مروري", value: "Accident" },
      { label: "سرقة", value: "Theft" },
    ],
    default: "Accident",
    required: true,
  },
  { name: "incident_date", type: "date", label: "تاريخ الحادث", required: true },
  { name: "incident_time", type: "time", label: "وقت الحادث" },
  { name: "location", label: "الموقع" },
  { name: "odometer_at_incident", type: "number", label: "قراءة العداد" },
  { name: "description", type: "textarea", rows: 5, label: "وصف ما حدث", required: true },
  { name: "evidence", type: "file", label: "صور أو مستند" },
];
</script>
<template>
  <ActionForm title="بلاغ حادث" intro="تُربط المركبة والمندوب بحسابك تلقائياً. بيانات التأمين والمعالجة للمختصين." :fields="fields" :resource="resource" action-key="incident" />
</template>
