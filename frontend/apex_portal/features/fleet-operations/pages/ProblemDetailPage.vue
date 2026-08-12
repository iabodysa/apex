<script setup>
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button } from "frappe-ui";
import { createFleetOperationsResources } from "../api.js";
const route = useRoute(),
    resource = createFleetOperationsResources().problem,
    doc = computed(() => resource.data || null);
onMounted(() => resource.fetch({ name: route.params.name }));
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>بلاغ تشغيلي</p>
                <h2>
                    <bdi>{{ route.params.name }}</bdi>
                </h2>
            </div>
            <Button
                variant="outline"
                icon="refresh-cw"
                label="تحديث"
                @click="resource.fetch({ name: route.params.name })"
            />
        </header>
        <div v-if="resource.loading" class="ops-state">جاري تحميل البلاغ…</div>
        <article v-else-if="doc" class="ops-card">
            <Badge theme="green" :label="doc.status" />
            <h3>{{ doc.subject }}</h3>
            <p>{{ doc.description }}</p>
            <h3>المحادثة</h3>
            <ol>
                <li v-for="item in doc.communications || []" :key="item.name">
                    <strong>{{ item.sender }}</strong>
                    <p>{{ item.content }}</p>
                </li>
            </ol>
        </article>
        <div v-else class="ops-state ops-state--error">البلاغ غير موجود أو خارج نطاق مشروعك.</div>
    </section>
</template>
