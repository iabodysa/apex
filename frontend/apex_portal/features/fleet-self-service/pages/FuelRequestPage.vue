<script setup>
import ActionForm from "../components/ActionForm.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().requestFuel;
const fields = [
    { name: "litres", type: "number", label: "الكمية باللتر", required: true },
    { name: "station", label: "محطة الوقود" },
    { name: "notes", type: "textarea", rows: 3, label: "ملاحظة" },
];
</script>
<template>
    <ActionForm
        title="طلب وقود"
        intro="الطلب العادي مرتبط بحصتك الشهرية الحالية."
        :fields="fields"
        :resource="resource"
        action-key="standard-fuel"
    />
</template>
