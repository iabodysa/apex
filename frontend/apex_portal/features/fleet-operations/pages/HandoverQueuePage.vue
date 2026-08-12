<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().handovers;
</script>
<template>
    <QueuePage title="قائمة الاستلام" :resource="resource" empty="لا توجد مستندات استلام معلقة." />
</template>
