<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import ActionForm from "../components/ActionForm.vue";
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
  [{ label: "بدون تحديد", value: "" }].concat(
    (stations.data || []).map((name) => ({ label: name, value: name })),
  ),
);
const stationField = computed(() => {
  if (stations.loading) return { disabled: true, description: "جارٍ تحميل محطات الوقود…" };
  if (stations.error) return { disabled: true, description: "تعذّر تحميل محطات الوقود، ويمكنك الإرسال بدون تحديدها." };
  if (!stations.data?.length) return { disabled: true, description: "لا توجد محطة وقود نشطة، ويمكنك الإرسال بدون تحديدها." };
  return { disabled: false, description: "" };
});
const fields = computed(() => [
  { name: "litres", type: "number", label: "الكمية باللتر", required: true },
  {
    name: "station",
    type: "select",
    label: "محطة الوقود",
    options: stationOptions.value,
    ...stationField.value,
  },
  { name: "notes", type: "textarea", rows: 3, label: "ملاحظة" },
]);
</script>
<template>
  <ActionForm title="طلب وقود" intro="الطلب العادي مرتبط بحصتك الشهرية الحالية." :fields="fields" :resource="resource" action-key="standard-fuel" />
</template>
