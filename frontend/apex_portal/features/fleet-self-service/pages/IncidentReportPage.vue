<script setup>
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.report_incident",
  method: "POST",
  auto: false,
});
const fields = [
  {
    name: "incident_type",
    type: "select",
    label: __("Type of Incident"),
    options: [
      { label: __("Traffic Accident"), value: "Accident" },
      { label: __("Theft"), value: "Theft" },
    ],
    default: "Accident",
    required: true,
  },
  { name: "incident_date", type: "date", label: __("Date of the Incident"), required: true },
  { name: "incident_time", type: "time", label: __("Incident Time") },
  { name: "location", label: __("Location") },
  { name: "odometer_at_incident", type: "number", label: __("Current Odometer Reading") },
  { name: "description", type: "textarea", rows: 5, label: __("Description of What Happened"), required: true },
  { name: "evidence", type: "file", label: __("Photos or Document") },
];
</script>
<template>
  <ActionForm :title="__('Incident Report')" :intro="__('The vehicle and representative are linked to your account automatically. Insurance and processing details are for specialists.')" :fields="fields" :resource="resource" action-key="incident" />
</template>
