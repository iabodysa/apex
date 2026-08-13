<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import { statusLabel } from "../../../core/displayLabels.js";
const props = defineProps({
    title: String,
    resource: Object,
    rowsKey: { type: String, default: "" },
    detailBase: { type: String, default: "" },
    empty: String,
});
const rows = computed(() => {
    const data = props.resource.data;
    if (props.rowsKey) return data?.[props.rowsKey] || [];
    return Array.isArray(data) ? data : data?.rows || [];
});
onMounted(() => props.resource.fetch());
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>تشغيل سلس</p>
                <h2>{{ title }}</h2>
            </div>
            <Button
                variant="outline"
                icon="refresh-cw"
                label="تحديث"
                :loading="resource.loading"
                @click="resource.fetch()"
            />
        </header>
        <div v-if="resource.loading && !rows.length" class="ops-state" role="status">
            جاري تحميل القائمة…
        </div>
        <div v-else-if="resource.error" class="ops-state ops-state--error">
            <strong>تعذر تحميل القائمة</strong
            ><Button variant="outline" label="حاول مرة ثانية" @click="resource.fetch()" />
        </div>
        <div v-else-if="!rows.length" class="ops-state">{{ empty }}</div>
        <div v-else class="ops-table" role="table">
            <RouterLink
                v-for="row in rows"
                :key="row.name || row.vehicle || row.plate"
                :to="
                    detailBase
                        ? `${detailBase}/${encodeURIComponent(row.name || row.vehicle || row.plate)}`
                        : ''
                "
                class="ops-row"
                ><div>
                    <strong
                        ><bdi>{{
                            row.vehicle_plate || row.plate || row.subject || row.name
                        }}</bdi></strong
                    ><span>{{
                        row.driver_name || row.driver || row.project || row.location || ""
                    }}</span>
                </div>
                <Badge theme="green" :label="statusLabel(row.status || row.vehicle_status || 'Open')"
            /></RouterLink>
        </div>
    </section>
</template>
