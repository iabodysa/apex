<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import ResourceListPage from "../components/ResourceListPage.vue";
const route = useRoute();
const params = computed(() => ({ doctype: "Maintenance Request", name: route.params.name }));
</script>
<template><ResourceListPage title="تفاصيل طلب الصيانة" endpoint="frappe.client.get" :params="params" /></template>
