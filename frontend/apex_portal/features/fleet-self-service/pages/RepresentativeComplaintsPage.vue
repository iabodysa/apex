<script setup>
import SimpleListPage from "../components/SimpleListPage.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().complaints;
</script>
<template>
    <SimpleListPage
        title="البلاغات والشكاوى"
        :resource="resource"
        empty="لا توجد بلاغات مفتوحة أو سابقة."
        create-to="/complaints/new"
    />
</template>
