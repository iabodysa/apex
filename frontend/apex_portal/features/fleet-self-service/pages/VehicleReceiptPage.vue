<script setup>
import ActionForm from "../components/ActionForm.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().receiveVehicle;
const fields = [
    { name: "odometer", type: "number", label: "قراءة العداد", required: true },
    {
        name: "fuel_level",
        type: "select",
        label: "مستوى الوقود",
        options: ["Empty", "Quarter", "Half", "Three Quarters", "Full"],
    },
    { name: "condition_notes", type: "textarea", rows: 3, label: "ملاحظات الحالة" },
    { name: "signed_evidence", type: "file", label: "إثبات الاستلام" },
];
</script>
<template>
    <ActionForm
        title="استلام المركبة"
        intro="راجع المركبة وسجل القراءة الفعلية قبل التأكيد."
        :fields="fields"
        :resource="resource"
        action-key="vehicle-receipt"
    />
</template>
