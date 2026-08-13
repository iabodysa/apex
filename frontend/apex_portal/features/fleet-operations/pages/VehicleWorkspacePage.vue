<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, FormControl } from "frappe-ui";
import { createFleetOperationsResources } from "../api.js";
import { actionAvailability, createSingleFlight } from "../state.js";
import { statusLabel } from "../../../core/displayLabels.js";
const route = useRoute(),
    r = createFleetOperationsResources(),
    vehicle = computed(() => {
        const list = r.vehicles.data?.vehicles || [];
        return list.find((v) => (v.name || v.plate) === route.params.vehicle) || null;
    }),
    timeline = computed(() => r.vehicleTimeline.data?.events || []),
    notice = ref(""),
    reason = ref(""),
    once = createSingleFlight();
async function load() {
    await Promise.all([
        r.vehicles.fetch(),
        r.vehicleTimeline.fetch({ plate: route.params.vehicle }),
    ]);
}
async function act(name) {
    const cap = vehicle.value?.capabilities?.[name] || {
        allowed: false,
        reason: "الإجراء غير متاح لهذه الحالة.",
    };
    const state = actionAvailability(cap);
    if (state.disabled) {
        notice.value = state.reason;
        return;
    }
    await once(`${name}:${route.params.vehicle}`, () =>
        r[name].submit({ plate: route.params.vehicle, reason: reason.value || undefined }),
    );
    notice.value = "تم تنفيذ الإجراء";
    await load();
}
onMounted(load);
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>مساحة المركبة</p>
                <h2>
                    <bdi>{{ vehicle?.plate || route.params.vehicle }}</bdi>
                </h2>
            </div>
            <Badge
                v-if="vehicle"
                theme="green"
                :label="statusLabel(vehicle.vehicle_status || vehicle.status)"
            />
        </header>
        <div v-if="r.vehicles.loading" class="ops-state">جاري تحميل المركبة…</div>
        <div v-else-if="r.vehicles.error" class="ops-state ops-state--error">
            <p>تعذر تحميل المركبة.</p>
            <Button variant="outline" label="إعادة المحاولة" @click="load" />
        </div>
        <div v-else-if="!vehicle" class="ops-state ops-state--error">
            المركبة غير موجودة أو خارج نطاق مشروعك.
        </div>
        <div v-else class="ops-workspace">
            <main class="ops-panels">
                <article class="ops-card">
                    <h3>الحالة والتشغيل</h3>
                    <p>
                        {{ vehicle.project || "—" }} ·
                        {{ vehicle.current_driver?.name_en || "من دون مندوب" }}
                    </p>
                    <div class="ops-actions">
                        <Button
                            variant="outline"
                            label="إيقاف"
                            :disabled="vehicle.capabilities?.stop?.allowed === false"
                            :title="vehicle.capabilities?.stop?.reason"
                            @click="act('stop')"
                        /><Button
                            variant="outline"
                            label="إدخال الورشة"
                            :disabled="vehicle.capabilities?.workshopIn?.allowed === false"
                            :title="vehicle.capabilities?.workshopIn?.reason"
                            @click="act('workshopIn')"
                        /><Button
                            variant="outline"
                            label="إخراج من الورشة"
                            :disabled="vehicle.capabilities?.workshopOut?.allowed === false"
                            :title="vehicle.capabilities?.workshopOut?.reason"
                            @click="act('workshopOut')"
                        /><Button
                            variant="solid"
                            theme="green"
                            label="إعادة للخدمة"
                            :disabled="vehicle.capabilities?.recover?.allowed === false"
                            :title="vehicle.capabilities?.recover?.reason"
                            @click="act('recover')"
                        />
                    </div>
                    <FormControl
                        v-model="reason"
                        type="textarea"
                        :rows="2"
                        label="ملاحظة الإجراء"
                    />
                    <p v-if="notice" class="ops-reason">{{ notice }}</p>
                </article>
                <article class="ops-card">
                    <h3>الالتزام</h3>
                    <p>{{ statusLabel(vehicle.compliance_status || "Not Tracked") }}</p>
                </article>
                <article class="ops-card">
                    <h3>الاسترداد والمعالجة</h3>
                    <p>تظهر قرارات الحوادث والتكاليف هنا من السجلات المعتمدة.</p>
                </article>
            </main>
            <aside class="ops-card">
                <h3>السجل الزمني</h3>
                <p v-if="r.vehicleTimeline.loading" class="ops-state" role="status">
                    جاري تحميل السجل الزمني…
                </p>
                <div v-else-if="r.vehicleTimeline.error" class="ops-state ops-state--error">
                    <p>تعذر تحميل السجل الزمني.</p>
                    <Button
                        class="timeline-retry"
                        variant="outline"
                        label="إعادة المحاولة"
                        @click="r.vehicleTimeline.fetch({ plate: route.params.vehicle })"
                    />
                </div>
                <p v-else-if="!timeline.length" class="ops-state">لا توجد أحداث مسجلة.</p>
                <ol v-else>
                    <li v-for="event in timeline" :key="`${event.kind}:${event.ref_name}`">
                        <strong>{{ event.title }}</strong>
                        <p>
                            <bdi>{{ event.date }}</bdi>
                        </p>
                    </li>
                </ol>
            </aside>
        </div>
    </section>
</template>
