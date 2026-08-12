<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().incidents;
</script>
<template>
    <QueuePage
        title="الحوادث"
        :resource="resource"
        detail-base="/incidents"
        empty="لا توجد حوادث ضمن مشاريعك."
    />
</template>
