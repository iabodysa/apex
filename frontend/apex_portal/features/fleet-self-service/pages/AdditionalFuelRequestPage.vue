<script setup>
import ActionForm from "../components/ActionForm.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().requestAdditionalFuel;
const fields = [
    { name: "topup_litres", type: "number", label: "الزيادة المطلوبة باللتر", required: true },
    { name: "reason", type: "textarea", rows: 4, label: "سبب الزيادة", required: true },
];
</script>
<template>
    <ActionForm
        title="طلب زيادة وقود"
        intro="يرسل الطلب للمشرف، ولا يضاف الرصيد قبل الاعتماد."
        :fields="fields"
        :resource="resource"
        action-key="additional-fuel"
    />
</template>
