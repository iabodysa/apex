<script setup>
import { computed, onMounted } from "vue";
import { Button, createResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { __ } from "../../../core/i18n.js";
const r = createResource({
    url: "apex.salis.api.fleet_os.get_operations_overview",
    method: "GET",
    auto: false,
  }),
  summary = computed(() => r.data?.summary || {});
onMounted(() => r.fetch());
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>{{ __("Salis Go-Live") }}</p>
        <h2>{{ __("Overview") }}</h2>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" :label="__('Refresh')" :loading="r.loading" @click="r.fetch()" />
    </header>
    <PortalSkeleton v-if="r.loading" :rows="3" :label="__('Loading operations metrics')" />
    <PortalErrorState v-else-if="r.error" :title="__('Could not load the metrics')" :message="r.error" @retry="r.fetch()" />
    <div v-else class="ops-metrics">
      <RouterLink
        v-for="item in [
          { key: 'vehicles', label: __('Vehicles'), to: '/vehicles' },
          { key: 'assignments', label: __('Assignment'), to: '/assignments' },
          { key: 'fuel_pending', label: __('Fuel Requests'), to: '/fuel-approvals' },
          { key: 'incidents_open', label: __('Open Incident Records'), to: '/incidents' },
        ]"
        :key="item.key"
        class="ops-metric"
        :to="item.to"
      >
        <strong>
          <bdi>{{ summary[item.key] || 0 }}</bdi>
        </strong>
        <span>{{ item.label }}</span>
      </RouterLink>
    </div>
  </section>
</template>
