<script setup>
import { computed, onMounted, ref } from "vue";
import { Badge, Button, Dialog, FormControl } from "frappe-ui";
import { createFleetOperationsResources } from "../api.js";
import { actionAvailability, createSingleFlight } from "../state.js";
const r = createFleetOperationsResources(),
    rows = computed(() => r.fuelQueue.data || []),
    selected = ref(null),
    reason = ref(""),
    once = createSingleFlight();
onMounted(() => r.fuelQueue.fetch());
async function act(kind, row) {
    const availability = actionAvailability(row.capabilities?.[kind] || { allowed: true });
    if (availability.disabled) return;
    await once(`${kind}:${row.name}`, () =>
        r[kind === "approve" ? "approveFuel" : "rejectFuel"].submit({
            name: row.name,
            reason: reason.value || undefined,
        }),
    );
    selected.value = null;
    reason.value = "";
    await r.fuelQueue.fetch();
}
</script>
<template>
    <section class="ops-page">
        <header class="ops-heading">
            <div>
                <p>تشغيل سلس</p>
                <h2>اعتماد الوقود</h2>
            </div>
            <Button
                variant="outline"
                icon="refresh-cw"
                label="تحديث"
                @click="r.fuelQueue.fetch()"
            />
        </header>
        <div v-if="r.fuelQueue.loading" class="ops-state">جاري تحميل الطلبات…</div>
        <div v-else-if="r.fuelQueue.error" class="ops-state ops-state--error">
            <p>تعذر تحميل طلبات الوقود.</p>
            <Button
                class="ops-retry"
                variant="outline"
                label="إعادة المحاولة"
                @click="r.fuelQueue.fetch()"
            />
        </div>
        <div v-else-if="!rows.length" class="ops-state">لا توجد طلبات بانتظار الاعتماد.</div>
        <div v-else class="ops-table">
            <article v-for="row in rows" :key="row.name" class="ops-row">
                <div>
                    <strong
                        ><bdi>{{ row.vehicle_plate || row.vehicle }}</bdi></strong
                    ><span
                        ><bdi>{{ row.topup_litres || row.requested_litres }} لتر</bdi> ·
                        {{ row.request_type }}</span
                    >
                </div>
                <div class="ops-actions">
                    <Badge theme="orange" :label="row.status" /><Button
                        variant="solid"
                        theme="green"
                        label="اعتماد"
                        :disabled="row.capabilities?.approve?.allowed === false"
                        :title="row.capabilities?.approve?.reason"
                        @click="act('approve', row)"
                    /><Button
                        variant="outline"
                        theme="red"
                        label="رفض"
                        :disabled="row.capabilities?.reject?.allowed === false"
                        :title="row.capabilities?.reject?.reason"
                        @click="selected = row"
                    />
                </div>
            </article>
        </div>
        <Dialog v-model="selected" :options="{ title: 'رفض طلب الوقود' }"
            ><template #body-content
                ><FormControl
                    v-model="reason"
                    type="textarea"
                    :rows="3"
                    label="سبب الرفض"
                    required /><Button
                    variant="solid"
                    theme="red"
                    label="تأكيد الرفض"
                    :loading="r.rejectFuel.loading"
                    @click="act('reject', selected)" /></template
        ></Dialog>
    </section>
</template>
