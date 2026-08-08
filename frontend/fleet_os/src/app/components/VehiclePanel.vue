<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Dialog v-model="open" :options="{ title: dialogTitle, size: '4xl' }">
    <template #body-content>
      <template v-if="vehicle">
        <div class="ph-left">
          <div class="ph-sub">
            {{ vehicle.vehicle_type || t("common.none") }} · {{ vehicle.rental_office || t("common.none") }}
            · <Icon :name="vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="13" />
            {{ vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike") }}
          </div>
          <div class="ph-tags">
            <Badge theme="gray" size="sm" :label="fmt.trim(vehicle.fuel) || t('common.none')" />
            <Badge theme="gray" size="sm" :label="fmt.trim(vehicle.project) || t('panel.noProject')" />
            <Badge theme="gray" size="sm" :label="fmt.trim(vehicle.area) || t('common.none')" />
            <Badge :theme="fmt.sb(vehicle).theme" size="sm" :label="fmt.sb(vehicle).label" />
          </div>
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
      </template>

      <!-- The panel reads the open plate out of the address against the board that is actually
           loaded, so a vehicle that leaves the supervisor's scope says so instead of freezing
           on the copy it was opened with. -->
      <EmptyState v-else :title="t('panel.gone')" :hint="t('panel.goneHint')">
        <template #icon><Icon name="car" :size="20" :stroke-width="1.6" /></template>
      </EmptyState>
    </template>
  </Dialog>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Dialog, TabButtons } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";

import Icon from "../Icon.vue";
import DriverSection from "./panel/DriverSection.vue";
import IncidentList from "./panel/IncidentList.vue";
import LogSection from "./panel/LogSection.vue";
import OverviewSection from "./panel/OverviewSection.vue";
import StatusSection from "./panel/StatusSection.vue";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, panelVehicle } = useBoardContext();
const { panelTab, setPanelTab } = state;

const vehicle = computed(() => panelVehicle.value);

const open = computed({
  get: () => Boolean(state.openPlate.value),
  set: (value) => {
    if (!value) state.closeVehicle();
  },
});

const dialogTitle = computed(() => state.openPlate.value || t("panel.title"));

const tabButtons = computed(() => [
  { label: t("panel.overview"), value: "overview" },
  { label: t("panel.driver"), value: "driver" },
  { label: t("panel.status"), value: "status" },
  { label: t("panel.damages"), value: "damages" },
  { label: t("panel.accidents"), value: "accidents" },
  { label: t("panel.log"), value: "log" },
]);
</script>
