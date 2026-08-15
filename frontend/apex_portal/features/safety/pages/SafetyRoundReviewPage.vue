<script setup>
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, createDocumentResource, createListResource, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { cadenceLabel, statusLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";

const route = useRoute();
const error = ref("");
const canReview = (globalThis.window?.apex_portal?.capabilities || []).includes("safety_check");
const round = createDocumentResource({
  doctype: "Safety Round",
  name: route.params.name,
});
const executions = createListResource({
  doctype: "Safety Task Execution",
  fields: [
    "name", "task", "task.task_title as task_title", "execution_status",
    "execution_time", "executed_by", "findings", "priority", "notes",
    "evidence_photo", "linked_maintenance_request", "docstatus",
  ],
  filters: { safety_round: route.params.name },
  pageLength: 200,
  auto: true,
});
const submit = createResource({ url: "frappe.client.submit" });
const rows = computed(() => executions.data || []);
async function ratify() {
  error.value = "";
  try {
    if (round.doc?.docstatus === 0) {
      await submit.submit({ doc: { ...round.doc, doctype: "Safety Round" } });
    }
    toast.create({ type: "success", message: "تم اعتماد الجولة" });
    await Promise.all([round.reload(), executions.reload()]);
  } catch (exception) {
    error.value = safeErrorMessage(exception, "تعذر اعتماد الجولة.");
  }
}
</script>
<template>
  <section class="feature-page">
    <h2>مراجعة جولة السلامة</h2>
    <PortalSkeleton v-if="round.get.loading || executions.list.loading" :rows="3" label="جارٍ التحميل" />
    <ErrorMessage v-else-if="round.get.error || executions.list.error" message="تعذر تحميل الجولة." />
    <template v-else>
      <div class="feature-card">
        <div class="record-identity">
          <strong dir="auto">{{ round.doc?.building || "جولة سلامة" }}</strong>
          <bdi v-if="round.doc?.name" class="record-reference" dir="auto" translate="no">{{ round.doc.name }}</bdi>
        </div>
        <span>{{ cadenceLabel(round.doc?.cadence) }}</span>
      </div>
      <ul class="feature-page__list">
        <li v-for="row in rows" :key="row.name">
          <div class="record-identity">
            <strong dir="auto">{{ row.task_title || "بند سلامة" }}</strong>
            <bdi class="record-reference" dir="auto" translate="no">{{ row.task }}</bdi>
          </div>
          <span>{{ statusLabel(row.execution_status) }}<template v-if="row.priority"> · {{ statusLabel(row.priority) }}</template></span>
          <p v-if="row.findings">{{ row.findings }}</p>
          <p v-if="row.notes">{{ row.notes }}</p>
          <a v-if="row.evidence_photo" :href="row.evidence_photo" target="_blank" rel="noopener">
            <img class="safety-evidence" :src="row.evidence_photo" alt="صورة الملاحظة" />
          </a>
          <RouterLink v-if="row.linked_maintenance_request" :to="`/maintenance/${row.linked_maintenance_request}`">طلب الصيانة <bdi dir="auto" translate="no">{{ row.linked_maintenance_request }}</bdi></RouterLink>
        </li>
      </ul>
      <ErrorMessage v-if="error" :message="error" />
      <Button v-if="canReview && round.doc?.docstatus === 0" theme="green" variant="solid" :loading="submit.loading" @click="ratify">اعتماد الجولة</Button>
      <p v-else-if="round.doc?.docstatus === 0" class="feature-page__empty">الجولة تنتظر مراجعة مشرف السكن.</p>
    </template>
  </section>
</template>
