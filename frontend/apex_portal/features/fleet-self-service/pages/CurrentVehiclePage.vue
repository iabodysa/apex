<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { createFleetSelfResources } from "../api.js";
const resource = createFleetSelfResources().vehicle;
const vehicle = computed(() => resource.data?.vehicle || null);
onMounted(() => resource.fetch());
</script>
<template>
    <section class="salis-page">
        <header class="salis-page__heading">
            <div>
                <p class="salis-eyebrow">عهدتك الحالية</p>
                <h2>المركبة</h2>
            </div>
            <Button variant="ghost" icon="refresh-cw" label="تحديث" @click="resource.fetch()" />
        </header>
        <AsyncPanel
            v-if="resource.loading"
            state="loading"
            title="جاري تحميل المركبة"
            message="لحظات وتظهر التفاصيل."
        /><AsyncPanel
            v-else-if="resource.error"
            state="error"
            title="تعذر تحميل المركبة"
            message="حاول مرة ثانية."
            @retry="resource.fetch()"
        /><AsyncPanel
            v-else-if="!vehicle"
            state="empty"
            title="لا توجد مركبة مسندة"
            message="ستظهر هنا بعد الإسناد من مشرف التشغيل."
        />
        <article v-else class="salis-card">
            <Badge theme="green" :label="vehicle.status || 'مسندة'" />
            <h3>
                <bdi>{{ vehicle.plate }}</bdi>
            </h3>
            <p>{{ vehicle.model || "الفئة غير محددة" }}</p>
            <dl>
                <div>
                    <dt>المشروع</dt>
                    <dd>{{ vehicle.office || "—" }}</dd>
                </div>
                <div>
                    <dt>قراءة العداد</dt>
                    <dd>
                        <bdi>{{ vehicle.odometerKm || 0 }} كم</bdi>
                    </dd>
                </div>
            </dl>
            <RouterLink class="salis-primary-link" to="/vehicle/receipt">تأكيد الاستلام</RouterLink
            ><RouterLink to="/vehicle/return">إرجاع المركبة</RouterLink>
        </article>
    </section>
</template>
