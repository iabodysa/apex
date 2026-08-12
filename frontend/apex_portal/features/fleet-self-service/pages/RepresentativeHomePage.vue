<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import { createFleetSelfResources } from "../api.js";
import AsyncPanel from "../components/AsyncPanel.vue";
const resources = createFleetSelfResources();
const context = computed(() => resources.context.data || {});
onMounted(() => resources.context.fetch());
</script>
<template>
    <section class="salis-page">
        <header>
            <p class="salis-eyebrow">مرحباً بك</p>
            <h2>خدمات سلس</h2>
        </header>
        <AsyncPanel
            v-if="resources.context.loading"
            state="loading"
            title="جاري تجهيز حسابك"
            message="نتحقق من مركبتك وخدماتك."
        /><AsyncPanel
            v-else-if="resources.context.error"
            state="error"
            title="تعذر تجهيز الحساب"
            message="حاول مرة ثانية."
            @retry="resources.context.fetch()"
        /><AsyncPanel
            v-else-if="context.state === 'unlinked'"
            state="empty"
            title="حسابك غير مرتبط بمندوب"
            message="راجع مشرف التشغيل لربط المستخدم ببياناتك."
        /><template v-else
            ><article class="salis-card">
                <div>
                    <p>المندوب</p>
                    <strong>{{ context.driver_name || "—" }}</strong>
                </div>
                <Badge theme="green" :label="context.assignment_status || 'جاهز'" />
                <p>
                    المركبة: <bdi>{{ context.vehicle_plate || "لا توجد مركبة مسندة" }}</bdi>
                </p>
            </article>
            <div class="salis-metrics">
                <RouterLink class="salis-metric" to="/vehicle"
                    ><strong>مركبتي</strong><span>الاستلام والإرجاع</span></RouterLink
                ><RouterLink class="salis-metric" to="/fuel"
                    ><strong>الوقود</strong><span>الرصيد والطلبات</span></RouterLink
                ><RouterLink class="salis-metric" to="/incidents"
                    ><strong>الحوادث</strong><span>بلاغاتك السابقة</span></RouterLink
                ><RouterLink class="salis-metric" to="/complaints"
                    ><strong>البلاغات</strong><span>المتابعة والردود</span></RouterLink
                >
            </div>
            <Button
                variant="outline"
                icon="refresh-cw"
                label="تحديث"
                @click="resources.context.fetch()"
        /></template>
    </section>
</template>
