<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { createFleetSelfResources } from "../api.js";
import { statusLabel } from "../../../core/displayLabels.js";
const r = createFleetSelfResources();
const quota = computed(() => r.quota.data?.quota || null);
onMounted(() => Promise.all([r.quota.fetch(), r.fuel.fetch()]));
</script>
<template>
    <section class="salis-page">
        <header class="salis-page__heading">
            <div>
                <p class="salis-eyebrow">هذا الشهر</p>
                <h2>رصيد الوقود</h2>
            </div>
            <Button variant="ghost" icon-left="refresh-cw" label="تحديث" @click="r.quota.fetch()" />
        </header>
        <AsyncPanel
            v-if="r.quota.loading"
            state="loading"
            title="جاري تحميل الرصيد"
            message="نراجع الحصة والاستهلاك."
        /><AsyncPanel
            v-else-if="r.quota.error"
            state="error"
            title="تعذر تحميل الرصيد"
            message="حاول مرة ثانية."
            @retry="r.quota.fetch()"
        /><AsyncPanel
            v-else-if="!quota"
            state="empty"
            title="لا توجد حصة نشطة"
            message="راجع مشرف التشغيل إذا كنت تحتاج حصة وقود."
        />
        <article v-else class="salis-card">
            <Badge theme="green" :label="statusLabel(quota.status)" />
            <div class="salis-metrics">
                <div class="salis-metric">
                    <strong
                        ><bdi>{{ quota.remaining_litres }} لتر</bdi></strong
                    ><span>المتبقي</span>
                </div>
                <div class="salis-metric">
                    <strong
                        ><bdi>{{ quota.monthly_litres }} لتر</bdi></strong
                    ><span>الحصة</span>
                </div>
            </div>
            <RouterLink class="salis-primary-link" to="/fuel/request">طلب وقود</RouterLink
            ><RouterLink to="/fuel/additional">طلب زيادة الحصة</RouterLink>
        </article>
    </section>
</template>
