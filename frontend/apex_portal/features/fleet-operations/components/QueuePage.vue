<script setup>
import { computed, inject, onBeforeUnmount, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { Badge, Button } from "frappe-ui";
import { recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
const props = defineProps({
    title: { type: String, required: true },
    resource: { type: Object, required: true },
    rowsKey: { type: String, default: "" },
    detailBase: { type: String, default: "" },
    empty: String,
    liveDoctype: { type: String, default: "" },
    liveEvent: { type: String, default: "" },
});
const rows = computed(() => {
    const data = props.resource.data;
    if (props.rowsKey) return data?.[props.rowsKey] || [];
    return Array.isArray(data) ? data : data?.rows || [];
});
const rowKey = (row) => row.name || row.vehicle || row.plate;
// A queue with no detail route must not dress its rows as links: an empty `to` resolves
// to the current path, so the tap is a silently aborted navigation that looks broken.
const rowBinding = (row) =>
    props.detailBase
        ? { is: RouterLink, to: `${props.detailBase}/${encodeURIComponent(rowKey(row))}` }
        : { is: "div" };
// A queue that names its room refetches when the room rings, so a second operator sees a
// vehicle leave the queue without pressing the refresh button beside the heading. The payload
// is a doorbell only: the rows are re-read through the same permission-scoped endpoint.
const subscribeDoctype = inject("portalDoctypeSubscribe", () => () => {});
let unsubscribe = () => {};
onMounted(() => {
    props.resource.fetch();
    if (props.liveDoctype && props.liveEvent) {
        unsubscribe = subscribeDoctype(props.liveDoctype, props.liveEvent, () => props.resource.fetch())
            || (() => {});
    }
});
onBeforeUnmount(() => unsubscribe());
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>تشغيل ساليس</p>
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
        <PortalSkeleton v-if="resource.loading && !rows.length" :rows="4" :label="`جارٍ تحميل ${title}`" />
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
            <component
                :is="rowBinding(row).is"
                v-for="row in rows"
                :key="rowKey(row)"
                v-bind="rowBinding(row).to ? { to: rowBinding(row).to } : {}"
                class="ops-row"
                ><div class="record-identity">
                    <strong dir="auto">{{ recordTitle(row, ["vehicle_plate", "plate", "subject", "driver_name", "project", "location"], title) }}</strong>
                    <bdi v-if="row.name" class="record-reference" dir="auto" translate="no">{{ row.name }}</bdi>
                    <span dir="auto">{{
                        row.driver_name || row.driver || row.project || row.location || ""
                    }}</span>
                </div>
                <Badge :theme="statusTheme(row.status || row.vehicle_status || 'Open')" :label="statusLabel(row.status || row.vehicle_status || 'Open')"
            /></component>
        </div>
    </section>
</template>
