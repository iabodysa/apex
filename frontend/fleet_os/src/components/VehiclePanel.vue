<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <aside v-if="wide" class="vehicle-context" :aria-label="t('panel.contextLabel')">
    <template v-if="state.openPlate.value">
      <VehicleWorkspace :vehicle="vehicle" />
    </template>
    <div v-else class="context-empty">
      <Icon name="car" :size="28" />
      <p>{{ t("panel.contextEyebrow") }}</p>
      <h2>{{ t("panel.selectTitle") }}</h2>
      <span>{{ t("panel.selectHint") }}</span>
    </div>
  </aside>

  <Dialog v-else v-model="open" :options="{ title: dialogTitle, size: '4xl' }">
    <template #body-content>
      <VehicleWorkspace :vehicle="vehicle" />
    </template>
  </Dialog>
</template>

<script setup>
import { computed } from "vue";
import { Dialog } from "frappe-ui";

import { useMediaQuery } from "@shared/useBreakpoint.js";

import Icon from "../Icon.vue";
import VehicleWorkspace from "./VehicleWorkspace.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, panelVehicle } = useBoardContext();
const wide = useMediaQuery("(min-width: 1180px)");
const vehicle = computed(() => panelVehicle.value);

const open = computed({
  get: () => Boolean(state.openPlate.value),
  set: (value) => {
    if (!value) state.closeVehicle();
  },
});

const dialogTitle = computed(() => state.openPlate.value || t("panel.title"));
</script>
