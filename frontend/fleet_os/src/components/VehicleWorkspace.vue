<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section v-if="vehicle" class="vehicle-workspace">
    <header class="vehicle-workspace-head">
      <div>
        <p>{{ t("panel.contextEyebrow") }}</p>
        <h2><bdi>{{ vehicle.plate }}</bdi></h2>
        <span>
          {{ vehicle.vehicle_type || t("common.none") }}
          <span aria-hidden="true">·</span>
          {{ vehicle.rental_office || t("common.none") }}
        </span>
      </div>
      <Button variant="ghost" size="lg" :label="t('panel.close')" @click="state.closeVehicle()">
        <template #icon><Icon name="x" :size="16" /></template>
      </Button>
    </header>

    <div class="vehicle-facts">
      <StatusLabel :tone="vehicleStatusTone(vehicle.vehicle_status)" :label="fmt.sb(vehicle).label" />
      <span>{{ fmt.trim(vehicle.project) || t("panel.noProject") }}</span>
      <span>{{ fmt.trim(vehicle.area) || t("common.none") }}</span>
      <span>{{ fmt.trim(vehicle.fuel) || t("common.none") }}</span>
    </div>

    <TabButtons
      class="panel-tabs"
      :buttons="tabButtons"
      :model-value="panelTab"
      @update:model-value="setPanelTab($event)"
    />

    <div class="panel-body">
      <OverviewSection v-if="panelTab === 'overview'" :vehicle="vehicle" />
      <DriverSection v-else-if="panelTab === 'driver'" :vehicle="vehicle" />
      <StatusSection v-else-if="panelTab === 'status'" :vehicle="vehicle" />
      <IncidentList v-else-if="panelTab === 'damages'" :vehicle="vehicle" kind="damages" />
      <IncidentList v-else-if="panelTab === 'accidents'" :vehicle="vehicle" kind="accidents" />
      <LogSection v-else :vehicle="vehicle" />
    </div>
  </section>

  <EmptyState v-else :title="t('panel.gone')" :hint="t('panel.goneHint')">
    <template #icon><Icon name="car" :size="20" /></template>
  </EmptyState>
</template>

<script setup>
import { computed } from "vue";
import { Button, TabButtons } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";

import Icon from "../Icon.vue";
import { vehicleStatusTone } from "../fleetHelpers.js";
import DriverSection from "./panel/DriverSection.vue";
import IncidentList from "./panel/IncidentList.vue";
import LogSection from "./panel/LogSection.vue";
import OverviewSection from "./panel/OverviewSection.vue";
import StatusSection from "./panel/StatusSection.vue";
import { useBoardContext } from "../boardContext.js";

defineProps({
  vehicle: { type: Object, default: null },
});

const { t, fmt, state } = useBoardContext();
const { panelTab, setPanelTab } = state;

const tabButtons = computed(() => [
  { label: t("panel.overview"), value: "overview" },
  { label: t("panel.driver"), value: "driver" },
  { label: t("panel.status"), value: "status" },
  { label: t("panel.damages"), value: "damages" },
  { label: t("panel.accidents"), value: "accidents" },
  { label: t("panel.log"), value: "log" },
]);

</script>
