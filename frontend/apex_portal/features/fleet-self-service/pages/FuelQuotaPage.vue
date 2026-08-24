<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { useResourceState } from "../../../core/useResourceState.js";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_fuel_quota",
  method: "GET",
  auto: false,
});
const quota = computed(() => resource.data?.quota || null);
const state = useResourceState(resource, () => !quota.value);
onMounted(() => resource.fetch());
</script>
<template>
  <section class="salis-page">
    <header class="salis-page__heading">
      <div>
        <p class="salis-eyebrow">{{ __("This Month") }}</p>
        <h2>{{ __("Fuel Balance") }}</h2>
      </div>
      <Button variant="ghost" icon-left="lucide-refresh-cw" :label="__('Refresh')" @click="resource.fetch()" />
    </header>
    <AsyncPanel v-if="state === 'loading'" state="loading" :title="__('Loading the balance')" :message="__('Reviewing the quota and consumption.')" />
    <AsyncPanel v-else-if="state === 'error'" state="error" :title="__('Could not load the balance')" :message="resource.error" @retry="resource.fetch()" />
    <AsyncPanel v-else-if="state === 'empty'" state="empty" :title="__('No Active Quota')" :message="__('Contact the operations supervisor if you need a fuel quota.')" />
    <article v-else class="salis-card">
      <Badge :theme="statusTheme(quota.status)" :label="statusLabel(quota.status)" />
      <div class="salis-metrics">
        <div class="salis-metric">
          <strong>
            <bdi>{{ __("{0} L", [quota.remaining_litres]) }}</bdi>
          </strong>
          <span>{{ __("Left") }}</span>
        </div>
        <div class="salis-metric">
          <strong>
            <bdi>{{ __("{0} L", [quota.monthly_litres]) }}</bdi>
          </strong>
          <span>{{ __("Quota") }}</span>
        </div>
      </div>
      <RouterLink class="salis-primary-link" to="/fuel/request">{{ __("Fuel Request") }}</RouterLink>
      <RouterLink to="/fuel/additional">{{ __("Request a Quota Increase") }}</RouterLink>
    </article>
  </section>
</template>
