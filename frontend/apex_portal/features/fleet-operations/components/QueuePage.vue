<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import { recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
const props = defineProps({
    title: { type: String, required: true },
    resource: { type: Object, required: true },
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
                icon="lucide-refresh-cw"
                label="تحديث"
                :loading="resource.loading"
                @click="resource.fetch()"
            />
        </header>
        <div v-if="resource.loading && !rows.length" class="ops-state" role="status">
            جاري تحميل القائمة…
        </div>
        <PortalErrorState
            v-else-if="resource.error"
            class="ops-state ops-state--error"
            title="تعذر تحميل القائمة"
            :message="resource.error"
            fallback="راجع صلاحيات القائمة أو الاتصال ثم حاول مرة أخرى."
            @retry="resource.fetch()"
        />
        <div v-else-if="!rows.length" class="ops-state">{{ empty }}</div>
        <div v-else class="ops-table">
            <RouterLink
                v-for="row in rows"
                :key="row.name || row.vehicle || row.plate"
                :to="
                    detailBase
                        ? `${detailBase}/${encodeURIComponent(row.name || row.vehicle || row.plate)}`
                        : ''
                "
                class="ops-row"
                ><div class="record-identity">
                    <strong dir="auto">{{ recordTitle(row, ["vehicle_plate", "plate", "subject", "driver_name", "project", "location"], title) }}</strong>
                    <bdi v-if="row.name" class="record-reference" dir="auto" translate="no">{{ row.name }}</bdi>
                    <span>{{
                        row.driver_name || row.driver || row.project || row.location || ""
                    }}</span>
                </div>
                <Badge :theme="statusTheme(row.status || row.vehicle_status || 'Open')" :label="statusLabel(row.status || row.vehicle_status || 'Open')"
            /></RouterLink>
        </div>
    </section>
</template>
