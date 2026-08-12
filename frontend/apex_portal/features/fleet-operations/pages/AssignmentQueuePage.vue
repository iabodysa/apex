<script setup>
import QueuePage from "../components/QueuePage.vue";
import { createFleetOperationsResources } from "../api.js";
const resource = createFleetOperationsResources().assignments;
</script>
<template>
    <QueuePage
        title="قائمة الإسناد"
        :resource="resource"
        empty="لا توجد عمليات إسناد تحتاج متابعة."
    />
</template>
