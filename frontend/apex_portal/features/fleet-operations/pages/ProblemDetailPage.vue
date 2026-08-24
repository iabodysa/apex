<script setup>
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, createResource } from "frappe-ui";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { __ } from "../../../core/i18n.js";
const route = useRoute(),
  resource = createResource({
    url: "apex.salis.api.fleet_os.get_problem_detail",
    method: "GET",
    auto: false,
  }),
  doc = computed(() => resource.data || null);
onMounted(() => resource.fetch({ name: route.params.name }));
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>{{ __("Operational Report") }}</p>
        <h2>{{ doc?.subject || __("Report Details") }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" :label="__('Refresh')" @click="resource.fetch({ name: route.params.name })" />
    </header>
    <PortalSkeleton v-if="resource.loading" :rows="3" :label="__('Loading the report')" />
    <PortalErrorState
      v-else-if="resource.error"
      :title="__('Could not open the report')"
      :message="resource.error"
      :fallback="__('Could not load the record. Check your connection, then try again.')"
      @retry="resource.fetch({ name: route.params.name })"
    />
    <article v-else-if="doc" class="ops-card">
      <Badge :theme="statusTheme(doc.status)" :label="statusLabel(doc.status)" />
      <h3>{{ doc.subject }}</h3>
      <p>{{ doc.description }}</p>
      <h3>{{ __("Conversation") }}</h3>
      <ol>
        <li v-for="item in doc.communications || []" :key="item.name">
          <strong><bdi dir="auto" translate="no">{{ item.sender }}</bdi></strong>
          <p dir="auto">{{ item.content }}</p>
        </li>
      </ol>
    </article>
    <div v-else class="ops-state ops-state--error">{{ __("The report does not exist or is outside your project's scope.") }}</div>
  </section>
</template>
