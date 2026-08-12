<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import AsyncPanel from "./AsyncPanel.vue";

const props = defineProps({
    title: String,
    resource: Object,
    rowsKey: { type: String, default: "" },
    empty: String,
    createTo: String,
});
const rows = computed(() => {
    const data = props.resource.data;
    if (props.rowsKey) return data?.[props.rowsKey] || [];
    return Array.isArray(data) ? data : [];
});
onMounted(() => props.resource.fetch());
</script>

<template>
    <section class="salis-page">
        <header class="salis-page__heading">
            <div>
                <p class="salis-eyebrow">سلس</p>
                <h2>{{ title }}</h2>
            </div>
            <Button
                variant="ghost"
                icon="refresh-cw"
                label="تحديث"
                :loading="resource.loading"
                @click="resource.fetch()"
            />
        </header>
        <RouterLink v-if="createTo" class="salis-primary-link" :to="createTo"
            >إضافة جديد</RouterLink
        >
        <AsyncPanel
            v-if="resource.loading && !rows.length"
            state="loading"
            title="جاري التحميل"
            message="نسترجع آخر البيانات المسجلة."
        />
        <AsyncPanel
            v-else-if="resource.error"
            state="error"
            title="تعذر تحميل البيانات"
            message="تحقق من الاتصال وحاول مرة ثانية."
            @retry="resource.fetch()"
        />
        <AsyncPanel
            v-else-if="!rows.length"
            state="empty"
            title="لا توجد سجلات"
            :message="empty"
        />
        <ul v-else class="salis-list">
            <li v-for="row in rows" :key="row.name || row.id">
                <div>
                    <strong
                        ><bdi>{{
                            row.subject || row.incident_type || row.type || row.name
                        }}</bdi></strong
                    >
                    <p>
                        {{
                            row.description ||
                            row.vehicle_plate ||
                            row.location ||
                            row.project ||
                            ""
                        }}
                    </p>
                </div>
                <Badge theme="green" variant="subtle" :label="row.status || 'مفتوح'" />
            </li>
        </ul>
    </section>
</template>
