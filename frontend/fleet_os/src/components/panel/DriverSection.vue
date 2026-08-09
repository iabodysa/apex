<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <template v-if="vehicle.current_driver && vehicle.vehicle_status === 'assigned'">
    <Alert
      theme="green"
      :title="t('driverTab.lockedFor', { name: driverName })"
      :dismissable="false"
    />

    <h3 class="psect-title">{{ t("driverTab.currentDriverData") }}</h3>
    <dl class="kv-grid">
      <div v-for="row in driverRows" :key="row.label" class="kv">
        <dt class="kv-l">{{ row.label }}</dt>
        <dd class="kv-v" :class="{ mono: row.mono }">
          <bdi v-if="row.mono">{{ row.value }}</bdi>
          <template v-else>{{ row.value }}</template>
        </dd>
      </div>
    </dl>

    <h3 class="psect-title">{{ t("driverTab.actions") }}</h3>
    <div class="panel-actions">
      <Button variant="solid" theme="red" size="xl" :label="t('driverTab.stopAndLock')" @click="actions.openStopForm()">
        <template #prefix><Icon name="circle-pause" :size="15" /></template>
      </Button>
      <Button variant="outline" theme="green" size="xl" :label="t('driverTab.reassignNew')" @click="assignment.openReassignForm()">
        <template #prefix><Icon name="rotate-cw" :size="15" /></template>
      </Button>
    </div>

    <StopForm v-if="subForm === 'stop'" />
    <ReassignForm v-else-if="subForm === 'reassign'" :vehicle="vehicle" />
  </template>

  <template v-else>
    <Alert
      v-if="vehicle.vehicle_status === 'workshop'"
      theme="yellow"
      :title="t('driverTab.inWorkshopHint')"
      :dismissable="false"
    />
    <Alert
      v-else-if="vehicle.vehicle_status === 'stopped'"
      theme="yellow"
      :title="t('driverTab.stoppedHint')"
      :dismissable="false"
    />

    <Alert
      v-else-if="vehicle.vehicle_status === 'stolen'"
      theme="red"
      :title="t('driverTab.stolenHint')"
      :dismissable="false"
    />

    <template v-if="!vehicle.current_driver && vehicle.vehicle_status === 'available'">
      <h3 class="psect-title">{{ t("driverTab.assignNewDriver") }}</h3>
      <ReassignForm :vehicle="vehicle" />
    </template>

    <div v-else class="panel-actions">
      <Button
        v-if="vehicle.vehicle_status === 'workshop'"
        variant="solid"
        theme="green"
        size="xl"
        :label="t('statusTab.exitWorkshop')"
        @click="actions.exitWorkshop(vehicle.plate)"
      />
      <Button
        v-else-if="vehicle.vehicle_status === 'stolen'"
        variant="solid"
        theme="green"
        size="xl"
        :label="t('statusTab.recoverVehicle')"
        @click="actions.recoverVehicle(vehicle.plate)"
      />
      <Button
        v-else-if="vehicle.vehicle_status === 'stopped'"
        variant="solid"
        theme="green"
        size="xl"
        :label="t('card.available')"
        @click="actions.setAvailable(vehicle.plate)"
      />
    </div>
  </template>
</template>

<script setup>
import { computed } from "vue";
import { Alert, Button } from "frappe-ui";

import Icon from "../../Icon.vue";
import ReassignForm from "./ReassignForm.vue";
import StopForm from "./StopForm.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
});

const { t, actions, assignment, subForm } = useBoardContext();

const driverName = computed(() => {
  const d = props.vehicle.current_driver;
  return d ? d.name_ar || d.name_en || "" : "";
});

const driverRows = computed(() => {
  const d = props.vehicle.current_driver || {};
  return [
    { label: t("driverTab.nameAr"), value: d.name_ar || t("common.none") },
    { label: t("driverTab.nameEn"), value: d.name_en || t("common.none") },
    { label: t("driverTab.iqama"), value: d.driver_id || t("common.none"), mono: true },
    { label: t("driverTab.mobile"), value: d.mobile || t("common.none"), mono: true },
    { label: t("driverTab.project"), value: (d.project || "").trim() || t("common.none") },
    { label: t("driverTab.area"), value: d.area || t("common.none") },
    { label: t("driverTab.receiveDate"), value: d.date_receive || t("common.none"), mono: true },
    { label: t("driverTab.receiveBranch"), value: d.branch_receive || t("common.none") },
  ];
});
</script>
