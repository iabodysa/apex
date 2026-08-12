<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().vehicles;
</script>
<template>
    <QueuePage
        title="المركبات"
        :resource="resource"
        rows-key="vehicles"
        detail-base="/vehicles"
        empty="لا توجد مركبات ضمن المشاريع المسموحة."
    />
</template>
