<script setup>
import { computed, onMounted } from "vue";
import { Button } from "frappe-ui";
import { createFleetOperationsResources } from "../api.js";
const r = createFleetOperationsResources().overview,
    summary = computed(() => r.data?.summary || {});
onMounted(() => r.fetch());
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>تشغيل سلس</p>
                <h2>نظرة عامة</h2>
            </div>
            <Button
                variant="outline"
                icon="refresh-cw"
                label="تحديث"
                :loading="r.loading"
                @click="r.fetch()"
            />
        </header>
        <div v-if="r.loading" class="ops-state">جاري تحميل مؤشرات التشغيل…</div>
        <div v-else-if="r.error" class="ops-state ops-state--error">تعذر تحميل المؤشرات.</div>
        <div v-else class="ops-metrics">
            <RouterLink
                v-for="item in [
                    { key: 'vehicles', label: 'المركبات', to: '/vehicles' },
                    { key: 'assignments', label: 'الإسناد', to: '/assignments' },
                    { key: 'fuel_pending', label: 'طلبات الوقود', to: '/fuel-approvals' },
                    { key: 'incidents_open', label: 'الحوادث المفتوحة', to: '/incidents' },
                ]"
                :key="item.key"
                class="ops-metric"
                :to="item.to"
                ><strong
                    ><bdi>{{ summary[item.key] || 0 }}</bdi></strong
                ><span>{{ item.label }}</span></RouterLink
            >
        </div>
    </section>
</template>
