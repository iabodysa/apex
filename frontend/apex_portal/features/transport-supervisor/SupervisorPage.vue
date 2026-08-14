<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, FeatherIcon, createDocumentResource, createResource } from "frappe-ui";
import { useRoute } from "vue-router";
import { dateTimeLabel, statusLabel, statusTheme } from "../../core/displayLabels.js";
import TripRequestAssignment from "./components/TripRequestAssignment.vue";
import RequestTripPlanning from "./components/RequestTripPlanning.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";
import { safeErrorMessage } from "../../core/errorMessage.js";
import { meaningfulRequestTitle } from "./assignmentState.js";

const route = useRoute();
const spec = route.meta.view || {};
const record = createDocumentResource({
  doctype: spec.doctype,
  name: route.params.name,
});
const transitions = createResource({
  url: "frappe.model.workflow.get_transitions",
  method: "POST",
  auto: false,
});
const workflow = createResource({
  url: "frappe.model.workflow.apply_workflow",
  method: "POST",
  auto: false,
});
const linkTitle = createResource({
  url: "frappe.client.get_value",
  method: "GET",
  auto: false,
});
const actionError = ref("");
const busyAction = ref("");
const linkLabels = ref({});
let linkLoadVersion = 0;
const doc = computed(() => record?.doc || null);
const state = computed(() => {
  if (record?.get.loading && !doc.value) return "loading";
  if (record?.get.error) return record.get.error?.status === 403 ? "denied" : "error";
  return doc.value ? "ready" : "empty";
});
const title = computed(() => {
  if (spec.doctype === "Transport Request") {
    return meaningfulRequestTitle(doc.value, spec.title);
  }
  return doc.value?.assignment_name || doc.value?.trip_title || spec.title;
});
const workflowActions = computed(() => [
  ...new Map(
    (transitions.data || []).map((item) => [
      `${item.action}:${item.next_state}`,
      item,
    ]),
  ).values(),
]);

const actionLabels = Object.freeze({
  Approve: "اعتماد",
  Reject: "رفض",
  Revise: "إعادة للمراجعة",
  Cancel: "إلغاء",
  Dispatch: "بدء التشغيل",
  Complete: "إكمال الرحلة",
});

function displayValue(field) {
  const value = doc.value?.[field.key];
  if (value === null || value === undefined || value === "") {
    return { label: "—", reference: "" };
  }
  if (["starts_on", "ends_on", "generated_through", "trip_date", "planned_start", "planned_end", "pickup_datetime"].includes(field.key)) {
    return { label: dateTimeLabel(value) || value, reference: "" };
  }
  if (field.key === "status") {
    return { label: statusLabel(value), reference: "" };
  }
  if (field.link) {
    return {
      label: doc.value?.[field.labelKey] || linkLabels.value[field.key] || field.link.fallback || "سجل مرتبط",
      reference: value,
    };
  }
  return { label: value, reference: "" };
}

async function loadLinkLabels(current) {
  const version = ++linkLoadVersion;
  const next = {};
  if (!current) {
    linkLabels.value = next;
    return;
  }
  for (const field of spec.fields || []) {
    const value = current[field.key];
    if (!field.link || !value) continue;
    try {
      const result = await linkTitle.fetch({
        doctype: field.link.doctype,
        filters: { name: value },
        fieldname: [field.link.fieldname],
      });
      const data = result?.message || result || {};
      next[field.key] = data[field.link.fieldname] || field.link.fallback || "سجل مرتبط";
    } catch {
      next[field.key] = field.link.fallback || "تعذّر جلب الاسم";
    }
  }
  if (version === linkLoadVersion) linkLabels.value = next;
}

async function loadTransitions(current) {
  if (!current) return;
  try {
    await transitions.fetch({ doc: JSON.stringify(current) });
  } catch {
    transitions.setData([]);
  }
}

async function applyAction(action) {
  actionError.value = "";
  busyAction.value = action;
  try {
    await workflow.submit({ doc: JSON.stringify(doc.value), action });
    await record.reload();
  } catch (reason) {
    actionError.value = safeErrorMessage(reason, "تعذّر تنفيذ الإجراء.");
  } finally {
    busyAction.value = "";
  }
}

watch(doc, loadTransitions, { immediate: true });
watch(doc, loadLinkLabels, { immediate: true });
</script>

<template>
  <section class="feature-page supervisor-detail" :aria-busy="state === 'loading'">
    <header class="feature-page__heading supervisor-detail__heading">
      <div>
        <p class="feature-page__eyebrow">تشغيل النقل</p>
        <h2 dir="auto">{{ title }}</h2>
        <bdi v-if="doc?.name" class="record-reference" dir="auto" translate="no">{{ doc.name }}</bdi>
      </div>
      <FeatherIcon :name="spec.icon || 'activity'" aria-hidden="true" />
    </header>

    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ تحميل السجل…</div>
    <PortalErrorState v-else-if="state === 'denied'" title="تعذّر فتح السجل" message="لا تملك صلاحية هذا السجل." @retry="record.reload" />
    <PortalErrorState v-else-if="state === 'error'" title="تعذّر تحميل السجل" :message="record.get.error" @retry="record.reload" />
    <div v-else-if="state === 'empty'" class="feature-state">السجل غير موجود.</div>

    <template v-else>
      <div class="supervisor-detail__status">
        <Badge :theme="statusTheme(doc.status)" :label="statusLabel(doc.status)" />
        <span v-if="doc.enabled === 0">متوقف</span>
      </div>

      <dl class="feature-details supervisor-detail__facts">
        <template v-for="field in spec.fields || []" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd>
            <span dir="auto">{{ displayValue(field).label }}</span>
            <bdi
              v-if="displayValue(field).reference"
              class="record-reference"
              dir="auto"
              translate="no"
            >{{ displayValue(field).reference }}</bdi>
          </dd>
        </template>
      </dl>

      <section v-if="doc.stops?.length" class="supervisor-detail__section">
        <header><h3>توقفات الرحلة</h3><span>{{ doc.stops.length }}</span></header>
        <ol class="supervisor-stop-list">
          <li v-for="stop in doc.stops" :key="stop.name || stop.stop_key">
            <bdi>{{ String(stop.idx || 0).padStart(2, '0') }}</bdi>
            <div><strong dir="auto">{{ stop.stop_name }}</strong><span dir="auto">{{ stop.location || stop.accommodation_building || 'الموقع غير محدد' }}</span></div>
            <span>{{ dateTimeLabel(stop.planned_time) || '—' }}</span>
          </li>
        </ol>
      </section>

      <section v-if="doc.assigned_requests?.length" class="supervisor-detail__section">
        <header><h3>الطلبات المسندة</h3><span>{{ doc.assigned_requests.length }}</span></header>
        <ol class="supervisor-assigned-list">
          <li v-for="request in doc.assigned_requests" :key="request.name || request.transport_request">
            <div class="record-identity">
              <strong dir="auto">{{ request.purpose || 'طلب نقل' }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ request.transport_request }}</bdi>
            </div>
            <span dir="auto">{{ request.pickup_stop }} ← {{ request.dropoff_stop }}</span>
            <span><bdi>{{ request.requested_count || 0 }}</bdi> راكب</span>
          </li>
        </ol>
      </section>

      <TripRequestAssignment
        v-if="spec.doctype === 'Dispatch Trip' && doc.status === 'Planned' && doc.stops?.length"
        :trip="doc"
        @saved="record.reload"
      />

      <RequestTripPlanning
        v-if="spec.doctype === 'Transport Request' && !doc.assigned_to_trip && ['Validated', 'Approved', 'Scheduled'].includes(doc.status)"
        :request="doc"
        @saved="record.reload"
      />

      <section v-if="doc.boarding_state?.length" class="supervisor-detail__section">
        <header><h3>قائمة الركاب</h3><span>{{ doc.boarding_state.length }}</span></header>
        <ol class="supervisor-passenger-list">
          <li v-for="passenger in doc.boarding_state" :key="passenger.passenger_key || passenger.name">
            <div><strong dir="auto">{{ passenger.passenger_name || 'راكب غير مسمى' }}</strong><span dir="auto">{{ passenger.pickup_stop }} ← {{ passenger.dropoff_stop }}</span></div>
            <Badge :theme="statusTheme(passenger.status)" :label="statusLabel(passenger.status)" />
          </li>
        </ol>
      </section>

      <p v-if="actionError" class="feature-error" role="alert">{{ actionError }}</p>
      <div v-if="workflowActions.length" class="supervisor-detail__actions" aria-label="إجراءات السجل">
        <Button
          v-for="transition in workflowActions"
          :key="`${transition.action}:${transition.next_state}`"
          :theme="transition.action === 'Approve' || transition.action === 'Dispatch' ? 'green' : undefined"
          :variant="transition.action === 'Reject' || transition.action === 'Cancel' ? 'outline' : 'solid'"
          :loading="busyAction === transition.action"
          :disabled="Boolean(busyAction)"
          @click="applyAction(transition.action)"
        >
          {{ actionLabels[transition.action] || transition.action }}
        </Button>
      </div>
    </template>
  </section>
</template>
