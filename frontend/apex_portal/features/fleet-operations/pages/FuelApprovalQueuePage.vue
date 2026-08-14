<script setup>
import { computed, onMounted, ref } from "vue";
import { Badge, Button, Dialog, FormControl, createResource } from "frappe-ui";
import { actionAvailability, createSingleFlight } from "../state.js";
import { statusLabel } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
const fuelQueue = createResource({
    url: "apex.salis.api.fuel_console.get_pending_fuel_requests",
    method: "GET",
    auto: false,
  }),
  approveFuel = createResource({
    url: "apex.salis.api.fuel_console.approve_fuel_request",
    method: "POST",
    auto: false,
  }),
  rejectFuel = createResource({
    url: "apex.salis.api.fuel_console.reject_fuel_request",
    method: "POST",
    auto: false,
  }),
  rows = computed(() => fuelQueue.data || []),
  selected = ref(null),
  reason = ref(""),
  once = createSingleFlight();
onMounted(() => fuelQueue.fetch());
async function act(kind, row) {
  const availability = actionAvailability(row.capabilities?.[kind] || { allowed: true });
  if (availability.disabled) return;
  await once(`${kind}:${row.name}`, () =>
    (kind === "approve" ? approveFuel : rejectFuel).submit({
      name: row.name,
      reason: reason.value || undefined,
    }),
  );
  selected.value = null;
  reason.value = "";
  await fuelQueue.fetch();
}
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>تشغيل سلس</p>
        <h2>اعتماد الوقود</h2>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" label="تحديث" @click="fuelQueue.fetch()" />
    </header>
    <div v-if="fuelQueue.loading" class="ops-state">جاري تحميل الطلبات…</div>
    <PortalErrorState
      v-else-if="fuelQueue.error"
      title="تعذّر تحميل طلبات الوقود"
      :message="fuelQueue.error"
      @retry="fuelQueue.fetch()"
    />
    <div v-else-if="!rows.length" class="ops-state">لا توجد طلبات بانتظار الاعتماد.</div>
    <div v-else class="ops-table">
      <article v-for="row in rows" :key="row.name" class="ops-row">
        <div>
          <strong>
            <bdi>{{ row.vehicle_plate || row.vehicle }}</bdi>
          </strong>
          <span>
            <bdi>{{ row.topup_litres || row.requested_litres }} لتر</bdi>
            · {{ statusLabel(row.request_type) }}
          </span>
        </div>
        <div class="ops-actions">
          <Badge theme="orange" :label="statusLabel(row.status)" />
          <Button variant="solid" theme="green" label="اعتماد" :disabled="row.capabilities?.approve?.allowed === false" :title="row.capabilities?.approve?.reason" @click="act('approve', row)" />
          <Button variant="outline" theme="red" label="رفض" :disabled="row.capabilities?.reject?.allowed === false" :title="row.capabilities?.reject?.reason" @click="selected = row" />
        </div>
      </article>
    </div>
    <Dialog v-model="selected" :options="{ title: 'رفض طلب الوقود' }">
      <template #body-header>
        <header class="portal-dialog__head">
          <h3>رفض طلب الوقود</h3>
          <button type="button" class="portal-dialog__close" aria-label="إغلاق النافذة" @click="selected = null">×</button>
        </header>
      </template>
      <template #body-content>
        <FormControl v-model="reason" type="textarea" :rows="3" label="سبب الرفض" required />
        <Button variant="solid" theme="red" label="تأكيد الرفض" :loading="rejectFuel.loading" @click="act('reject', selected)" />
      </template>
    </Dialog>
  </section>
</template>
