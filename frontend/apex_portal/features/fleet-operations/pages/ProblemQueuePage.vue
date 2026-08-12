<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().problems;
</script>
<template>
    <QueuePage
        title="المشكلات والبلاغات"
        :resource="resource"
        detail-base="/problems"
        empty="لا توجد مشكلات ضمن مشاريعك."
    />
</template>
