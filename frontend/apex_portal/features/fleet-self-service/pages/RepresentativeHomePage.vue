<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { useResourceState } from "../../../core/useResourceState.js";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";
const contextResource = createResource({
  url: "apex.salis.api.fleet_employee.get_context",
  method: "GET",
  auto: false,
});
const context = computed(() => contextResource.data || {});
const state = useResourceState(contextResource, () => context.value.state === "unlinked");
const grants = new Set(globalThis.window?.apex_portal?.capabilities || []);
const can = (capability) => grants.has(capability);
onMounted(() => contextResource.fetch());
</script>
<template>
  <section class="salis-page">
    <header>
      <p class="salis-eyebrow">{{ __("Greetings") }}</p>
      <h2>{{ __("Salis Services") }}</h2>
    </header>
    <AsyncPanel v-if="state === 'loading'" state="loading" :title="__('Preparing your account')" :message="__('We are checking your vehicle and services.')" />
    <AsyncPanel v-else-if="state === 'error'" state="error" :title="__('Could not prepare the account')" :message="__('Try again.')" @retry="contextResource.fetch()" />
    <AsyncPanel v-else-if="state === 'empty'" state="empty" :title="__('Your Account Is Not Linked to a Representative')" :message="__('Contact the operations supervisor to link the user to your data.')" />
    <template v-else>
      <article class="salis-card">
        <div>
          <p>{{ __("Representative") }}</p>
          <strong>{{ context.driver_name || "—" }}</strong>
        </div>
        <Badge :theme="statusTheme(context.assignment_status || 'assigned')" :label="statusLabel(context.assignment_status || 'assigned')" />
        <p>
          {{ __("The Vehicle") }}:
          <bdi>{{ context.vehicle_plate || __("No Vehicle Assigned") }}</bdi>
        </p>
      </article>
      <div class="salis-metrics">
        <RouterLink class="salis-metric" to="/vehicle">
          <strong>{{ __("My Vehicle") }}</strong>
          <span>{{ __("Receipt and Return") }}</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.fuel')" class="salis-metric" to="/fuel">
          <strong>{{ __("My Fuel") }}</strong>
          <span>{{ __("Balance and Requests") }}</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.incident')" class="salis-metric" to="/incidents">
          <strong>{{ __("Incidents") }}</strong>
          <span>{{ __("Your Past Complaints") }}</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.complaint')" class="salis-metric" to="/complaints">
          <strong>{{ __("My Complaints") }}</strong>
          <span>{{ __("Follow-up and Replies") }}</span>
        </RouterLink>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" :label="__('Refresh')" @click="contextResource.fetch()" />
    </template>
  </section>
</template>
