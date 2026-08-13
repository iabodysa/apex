<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, LoadingIndicator, createResource, toast } from "frappe-ui";
import { cadenceLabel, statusLabel } from "../../../core/displayLabels.js";

const route = useRoute();
const error = ref("");
const canReview = (globalThis.window?.apex_portal?.capabilities || []).includes("safety_check");
const round = createResource({
  url: "frappe.client.get",
  makeParams: () => ({ doctype: "Safety Round", name: route.params.name }),
});
const executions = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "Safety Task Execution",
    fields: ["name", "task", "execution_status", "notes", "evidence_photo", "linked_maintenance_request", "docstatus"],
    filters: { safety_round: route.params.name },
    limit_page_length: 200,
  }),
});
const submit = createResource({ url: "frappe.client.submit" });
const rows = computed(() => executions.data || []);
onMounted(() => Promise.all([round.fetch(), executions.fetch()]));
async function ratify() {
  error.value = "";
  try {
    if (round.data?.docstatus === 0) {
      await submit.submit({ doc: { ...round.data, doctype: "Safety Round" } });
    }
    toast.create({ type: "success", message: "تم اعتماد الجولة" });
    await Promise.all([round.fetch(), executions.fetch()]);
  } catch (exception) { error.value = exception.message || "تعذر اعتماد الجولة."; }
}
</script>
<template>
  <section class="feature-page"><h2>مراجعة جولة السلامة</h2>
    <LoadingIndicator v-if="round.loading || executions.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="round.error || executions.error" message="تعذر تحميل الجولة." />
    <template v-else>
      <div class="feature-card"><strong dir="auto">{{ round.data?.name }}</strong><span>{{ round.data?.building }} · {{ cadenceLabel(round.data?.cadence) }}</span></div>
      <ul class="feature-page__list">
        <li v-for="row in rows" :key="row.name">
          <strong dir="auto">{{ row.task }}</strong>
          <span>{{ statusLabel(row.execution_status) }}</span>
          <p v-if="row.notes">{{ row.notes }}</p>
          <a v-if="row.evidence_photo" :href="row.evidence_photo" target="_blank" rel="noopener">
            <img class="safety-evidence" :src="row.evidence_photo" alt="صورة الملاحظة" />
          </a>
          <RouterLink v-if="row.linked_maintenance_request" :to="`/maintenance/${row.linked_maintenance_request}`">
            طلب الصيانة {{ row.linked_maintenance_request }}
          </RouterLink>
        </li>
      </ul>
      <ErrorMessage v-if="error" :message="error" />
      <Button v-if="canReview && round.data?.docstatus === 0" variant="solid" :loading="submit.loading" @click="ratify">اعتماد الجولة</Button>
      <p v-else-if="round.data?.docstatus === 0" class="feature-page__empty">الجولة تنتظر مراجعة مشرف السكن.</p>
    </template>
  </section>
</template>
