<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.submit_fuel_request",
  method: "POST",
  auto: false,
});
// fuel_platform is a Link to Fuel Platform, so the station has to be picked from the
// active platforms the server already publishes — free text is refused on insert.
const stations = createResource({
  url: "apex.salis.api.fleet_employee.get_fuel_stations",
  auto: true,
});
const stationOptions = computed(() =>
  [{ label: __("Not Specified"), value: "" }].concat(
    (stations.data || []).map((name) => ({ label: name, value: name })),
  ),
);
const stationField = computed(() => {
  if (stations.loading) return { disabled: true, description: __("Loading fuel stations…") };
  if (stations.error) return { disabled: true, description: __("Could not load fuel stations; you can submit without selecting one.") };
  if (!stations.data?.length) return { disabled: true, description: __("No active fuel station exists; you can submit without selecting one.") };
  return { disabled: false, description: "" };
});
const fields = computed(() => [
  { name: "litres", type: "number", label: __("Quantity in Litres"), required: true },
  {
    name: "station",
    type: "select",
    label: __("Fuel Station"),
    options: stationOptions.value,
    ...stationField.value,
  },
  { name: "notes", type: "textarea", rows: 3, label: __("Note") },
]);
</script>
<template>
  <ActionForm :title="__('Fuel Request')" :intro="__('The regular request is tied to your current monthly quota.')" :fields="fields" :resource="resource" action-key="standard-fuel" />
</template>
