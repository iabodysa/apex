<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Badge, Button, Dialog, FormControl, createResource } from "frappe-ui";
import { actionAvailability, createSingleFlight } from "../state.js";
import { statusLabel } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { safeErrorMessage } from "../../../core/errorMessage.js";
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
  // Dialog speaks a boolean, so the open flag and the row under review are kept apart.
  rejectOpen = ref(false),
  selected = ref(null),
  reason = ref(""),
  actionError = ref(""),
  once = createSingleFlight();
onMounted(() => fuelQueue.fetch());
// A title attribute is invisible on a touch screen, so the refusal reason is rendered.
function availability(row, kind) {
  return actionAvailability(row.capabilities?.[kind] || { allowed: true });
}
function openReject(row) {
  selected.value = row;
  rejectOpen.value = true;
}
// Every close path lands here — the close button, Escape, and an outside click — so an
// abandoned reason never reappears in the next request's dialog.
watch(rejectOpen, (open) => {
  if (open) return;
  selected.value = null;
  reason.value = "";
  actionError.value = "";
});
async function act(kind, row) {
  const availability = actionAvailability(row.capabilities?.[kind] || { allowed: true });
  if (availability.disabled) return;
  actionError.value = "";
  try {
    await once(`${kind}:${row.name}`, () =>
      (kind === "approve" ? approveFuel : rejectFuel).submit({
        name: row.name,
        reason: reason.value || undefined,
      }),
    );
  } catch (caught) {
    // A refused decision must stay on screen with its reason; closing the dialog here
    // would read as success and invite a second press on the same request.
    actionError.value = safeErrorMessage(caught, "تعذّر تنفيذ القرار. حاول مرة أخرى.");
    return;
  }
  rejectOpen.value = false;
  await fuelQueue.fetch();
}
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>تشغيل ساليس</p>
        <h2>اعتماد الوقود</h2>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" label="تحديث" @click="fuelQueue.fetch()" />
    </header>
    <p v-if="actionError && !rejectOpen" class="ops-state ops-state--error" role="alert">{{ actionError }}</p>
    <PortalSkeleton v-if="fuelQueue.loading" :rows="3" label="جارٍ تحميل طلبات الوقود" />
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
          <Button variant="solid" theme="green" label="اعتماد" :disabled="availability(row, 'approve').disabled" @click="act('approve', row)" />
          <Button variant="outline" theme="red" label="رفض" :disabled="availability(row, 'reject').disabled" @click="openReject(row)" />
        </div>
        <p v-if="availability(row, 'approve').disabled" class="ops-row__reason">{{ availability(row, "approve").reason }}</p>
        <p v-else-if="availability(row, 'reject').disabled" class="ops-row__reason">{{ availability(row, "reject").reason }}</p>
      </article>
    </div>
    <Dialog v-model="rejectOpen" :options="{ title: 'رفض طلب الوقود' }">
      <template #body-header>
        <header class="portal-dialog__head">
          <h3>رفض طلب الوقود</h3>
          <button type="button" class="portal-dialog__close" aria-label="إغلاق النافذة" @click="rejectOpen = false">×</button>
        </header>
      </template>
      <template #body-content>
        <FormControl v-model="reason" type="textarea" :rows="3" label="سبب الرفض" required />
        <p v-if="actionError" class="ops-state ops-state--error" role="alert">{{ actionError }}</p>
        <Button variant="solid" theme="red" label="تأكيد الرفض" :loading="rejectFuel.loading" @click="act('reject', selected)" />
      </template>
    </Dialog>
  </section>
</template>
