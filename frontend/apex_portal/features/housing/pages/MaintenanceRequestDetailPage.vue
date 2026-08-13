<script setup>
import { useRoute } from "vue-router";
import { createDocumentResource } from "frappe-ui";
import ResourceListPage from "../components/ResourceListPage.vue";
import { statusLabel } from "../../../core/displayLabels.js";
const route = useRoute();
const request = createDocumentResource({
  doctype: "Maintenance Request",
  name: route.params.name,
});
</script>
<template>
  <ResourceListPage
    title="تفاصيل طلب الصيانة"
    :rows="request.doc ? [request.doc] : []"
    :loading="request.get.loading"
    :error="request.get.error"
    :refresh="request.reload"
    :title-fields="['issue_type']"
    fallback-title="طلب صيانة"
  >
    <template #row="{ row }">
      <div class="record-identity">
        <strong dir="auto">{{ row.issue_type || "طلب صيانة" }}</strong>
        <bdi class="record-reference" dir="auto" translate="no">{{ row.name }}</bdi>
      </div>
      <p v-if="row.issue_description">{{ row.issue_description }}</p>
      <span>{{ row.building }}<template v-if="row.room"> · {{ row.room }}</template></span>
      <small>{{ statusLabel(row.status) }}</small>
    </template>
  </ResourceListPage>
</template>
