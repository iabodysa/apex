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
    url: "apex.salis.api.fleet_os.get_incident_detail",
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
        <p>{{ __("Accident") }}</p>
        <h2 dir="auto">{{ doc?.vehicle_plate || doc?.vehicle || doc?.incident_type || __("Accident Details") }}</h2>
        <bdi class="record-reference" dir="auto" translate="no">{{ route.params.name }}</bdi>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" :label="__('Refresh')" @click="resource.fetch({ name: route.params.name })" />
    </header>
    <PortalSkeleton v-if="resource.loading" :rows="3" :label="__('Loading incident details')" />
    <PortalErrorState
      v-else-if="resource.error"
      :title="__('Could not open the incident')"
      :message="resource.error"
      :fallback="__('Could not load the record. Check your connection, then try again.')"
      @retry="resource.fetch({ name: route.params.name })"
    />
    <article v-else-if="doc" class="ops-card">
      <Badge :theme="statusTheme(doc.status)" :label="statusLabel(doc.status)" />
      <h3>{{ doc.incident_type }}</h3>
      <p>{{ doc.description }}</p>
      <dl>
        <div>
          <dt>{{ __("The Vehicle") }}</dt>
          <dd>
            <bdi>{{ doc.vehicle_plate || doc.vehicle }}</bdi>
          </dd>
        </div>
        <div>
          <dt>{{ __("Location") }}</dt>
          <dd>{{ doc.location || "—" }}</dd>
        </div>
      </dl>
      <p class="ops-reason">{{ __("Insurance, recovery, and closing actions come from the permissions the server returns.") }}</p>
    </article>
    <div v-else class="ops-state ops-state--error">{{ __("The record does not exist or is outside your project's scope.") }}</div>
  </section>
</template>
