<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().returns;
</script>
<template>
    <QueuePage
        title="قائمة الإرجاع"
        :resource="resource"
        empty="لا توجد مركبات بانتظار الإرجاع."
    />
</template>
