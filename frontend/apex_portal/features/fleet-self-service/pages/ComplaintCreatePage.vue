<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.create_complaint",
  method: "POST",
  auto: false,
});
const fields = [
  {
    name: "priority",
    type: "select",
    label: __("Priority"),
    options: [
      { label: __("Low"), value: "Low" },
      { label: __("Medium"), value: "Medium" },
      { label: __("High"), value: "High" },
      { label: __("Urgent"), value: "Urgent" },
    ],
    default: "Medium",
  },
  { name: "subject", label: __("Complaint Subject"), required: true },
  { name: "description", type: "textarea", rows: 5, label: __("Details"), required: true },
  { name: "attachment", type: "file", label: __("Attachment") },
];
</script>
<template>
  <ActionForm :title="__('New Complaint')" :intro="__('The complaint reaches the operations team and replies appear in the same record.')" :fields="fields" :resource="resource" action-key="complaint" />
</template>
