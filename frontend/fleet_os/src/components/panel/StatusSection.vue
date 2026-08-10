<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <h3 class="psect-title">{{ t("statusTab.title") }}</h3>

  <div class="status-grid">
    <button
      v-for="opt in options"
      :key="opt.key"
      type="button"
      class="stpick"
      :class="{ ['cur-' + opt.key]: vehicle.vehicle_status === opt.key }"
      :aria-current="vehicle.vehicle_status === opt.key ? 'true' : undefined"
      :disabled="optionDisabled(opt.key)"
      @click="chooseStatus(opt.key)"
    >
      <span class="sp-ico"><Icon :name="opt.icon" :size="20" /></span>
      <span class="sp-lbl">{{ opt.label }}</span>
      <span class="sp-desc">{{ opt.desc }}</span>
    </button>
  </div>

  <Button
    v-if="vehicle.vehicle_status === 'workshop'"
    class="fp-block-btn"
    variant="solid"
    theme="green"
    size="xl"
    :label="t('statusTab.exitWorkshop')"
    @click="actions.exitWorkshop(vehicle.plate)"
  >
    <template #prefix><Icon name="circle-check" :size="15" /></template>
  </Button>

  <Button
    v-if="vehicle.vehicle_status === 'stolen'"
    class="fp-block-btn"
    variant="solid"
    theme="green"
    size="xl"
    :label="t('statusTab.recoverVehicle')"
    @click="actions.recoverVehicle(vehicle.plate)"
  >
    <template #prefix><Icon name="lock-open" :size="15" /></template>
  </Button>

  <template v-if="canReportTheft">
    <h3 class="psect-title"><Icon name="shield-alert" :size="14" /> {{ t("statusTab.reportTheft") }}</h3>
    <Button
      class="fp-block-btn"
      variant="outline"
      theme="red"
      size="xl"
      :label="t('statusTab.reportTheftBtn')"
      @click="actions.openStolenForm()"
    >
      <template #prefix><Icon name="shield-alert" :size="15" /></template>
    </Button>
    <StolenForm v-if="subForm === 'stolen'" />
  </template>
</template>

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

import Icon from "../../Icon.vue";
import { canChooseVehicleStatus } from "../../fleetHelpers.js";
import StolenForm from "./StolenForm.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
});

const { t, actions, state, subForm } = useBoardContext();

const options = computed(() => [
  { key: "assigned", icon: "lock", label: t("statusTab.assignedLabel"), desc: t("statusTab.assignedDesc") },
  { key: "available", icon: "key", label: t("statusTab.availableLabel"), desc: t("statusTab.availableDesc") },
  { key: "workshop", icon: "wrench", label: t("statusTab.workshopLabel"), desc: t("statusTab.workshopDesc") },
  { key: "stopped", icon: "circle-pause", label: t("statusTab.stoppedLabel"), desc: t("statusTab.stoppedDesc") },
  { key: "stolen", icon: "shield-alert", label: t("statusTab.stolenLabel"), desc: t("statusTab.stolenDesc") },
]);

const canReportTheft = computed(() =>
  ["available", "stopped"].includes(props.vehicle.vehicle_status),
);

const optionDisabled = (key) =>
  !canChooseVehicleStatus(props.vehicle, key);

const chooseStatus = (key) => {
  if (key === "assigned") {
    state.setPanelTab("driver");
    return;
  }
  actions.changeStatus(props.vehicle.plate, key);
};
</script>
