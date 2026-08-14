<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, createDocumentResource, createResource } from "frappe-ui";
import { useRoute } from "vue-router";
import { statusLabel, statusTheme } from "../../core/displayLabels.js";
import TripRequestAssignment from "./components/TripRequestAssignment.vue";
import RequestTripPlanning from "./components/RequestTripPlanning.vue";
import SupervisorRecordFacts from "./components/SupervisorRecordFacts.vue";
import SupervisorRecordCollections from "./components/SupervisorRecordCollections.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";
import { safeErrorMessage } from "../../core/errorMessage.js";
import { meaningfulRequestTitle } from "./assignmentState.js";

const route = useRoute();
const spec = route.meta.view || {};
const fields = spec.fields || [];
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
const actionError = ref("");
const busyAction = ref("");
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
</script>

<template>
  <section class="feature-page supervisor-detail" :aria-busy="state === 'loading'">
    <header class="feature-page__heading supervisor-detail__heading">
      <div>
        <p class="feature-page__eyebrow">تشغيل النقل</p>
        <h2 dir="auto">{{ title }}</h2>
        <bdi v-if="doc?.name" class="record-reference" dir="auto" translate="no">{{ doc.name }}</bdi>
      </div>
      <span :class="spec.icon || 'lucide-activity'" aria-hidden="true" />
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

      <SupervisorRecordFacts :doc="doc" :fields="fields" />

      <SupervisorRecordCollections
        :stops="doc.stops"
        :assigned-requests="doc.assigned_requests"
        :passengers="doc.boarding_state"
      >
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
      </SupervisorRecordCollections>

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
