<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { useResourceState } from "../../../core/useResourceState.js";
import { statusLabel, statusTheme, vehicleCategoryLabel } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_vehicle",
  method: "GET",
  auto: false,
});
const vehicle = computed(() => resource.data?.vehicle || null);
const state = useResourceState(resource, () => !vehicle.value);
const canHandover = (globalThis.window?.apex_portal?.capabilities || []).includes("fleet.self.handover");
onMounted(() => resource.fetch());
</script>
<template>
  <section class="salis-page">
    <header class="salis-page__heading">
      <div>
        <p class="salis-eyebrow">{{ __("Your Current Custody") }}</p>
        <h2>{{ __("The Vehicle") }}</h2>
      </div>
      <Button variant="ghost" icon-left="lucide-refresh-cw" :label="__('Refresh')" @click="resource.fetch()" />
    </header>
    <AsyncPanel v-if="state === 'loading'" state="loading" :title="__('Loading the vehicle')" :message="__('Moments, and the details appear.')" />
    <AsyncPanel v-else-if="state === 'error'" state="error" :title="__('Could not load the vehicle')" :message="resource.error" @retry="resource.fetch()" />
    <AsyncPanel v-else-if="state === 'empty'" state="empty" :title="__('No Vehicle Assigned')" :message="__('It will appear here after assignment by the operations supervisor.')" />
    <article v-else class="salis-card">
      <Badge :theme="statusTheme(vehicle.status || 'assigned')" :label="statusLabel(vehicle.status || 'assigned')" />
      <h3>
        <bdi>{{ vehicle.plate }}</bdi>
      </h3>
      <p>{{ vehicleCategoryLabel(vehicle.model) || __("Category Not Specified") }}</p>
      <dl>
        <div>
          <dt>{{ __("Project") }}</dt>
          <dd>{{ vehicle.office || "—" }}</dd>
        </div>
        <div>
          <dt>{{ __("Current Odometer Reading") }}</dt>
          <dd>
            <bdi>{{ __("{0} km", [vehicle.odometerKm || 0]) }}</bdi>
          </dd>
        </div>
      </dl>
      <RouterLink v-if="canHandover" class="salis-primary-link" to="/vehicle/receipt">{{ __("Confirm Receipt") }}</RouterLink>
      <RouterLink v-if="canHandover" to="/vehicle/return">{{ __("Vehicle Return") }}</RouterLink>
    </article>
  </section>
</template>
