<script setup>
import ActionForm from "../components/ActionForm.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().createComplaint;
const fields = [
    {
        name: "priority",
        type: "select",
        label: "الأولوية",
        options: ["Low", "Medium", "High", "Urgent"],
        default: "Medium",
    },
    { name: "subject", label: "عنوان البلاغ", required: true },
    { name: "description", type: "textarea", rows: 5, label: "التفاصيل", required: true },
    { name: "attachment", type: "file", label: "مرفق" },
];
</script>
<template>
    <ActionForm
        title="بلاغ جديد"
        intro="يصل البلاغ إلى فريق التشغيل وتظهر الردود في نفس السجل."
        :fields="fields"
        :resource="resource"
        action-key="complaint"
    />
</template>
