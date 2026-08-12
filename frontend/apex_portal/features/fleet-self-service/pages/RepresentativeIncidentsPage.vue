<script setup>
import SimpleListPage from "../components/SimpleListPage.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().incidents;
</script>
<template>
    <SimpleListPage
        title="الحوادث"
        :resource="resource"
        empty="لا توجد حوادث مسجلة على مركبتك."
        create-to="/incidents/new"
    />
</template>
