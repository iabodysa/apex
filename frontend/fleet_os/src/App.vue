<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <FrappeUIProvider>
    <a class="fleet-skip" href="#fleet-main">{{ t("brand.skip") }}</a>

    <FleetPageShell>
    <template #brand>
      <Brand variant="reverse" size="32" />
      <bdi class="product-name" dir="ltr">{{ t("brand.name") }}</bdi>
    </template>

    <template #actions>
      <Button
        class="alert-bell"
        variant="outline"
        size="xl"
        :label="t('alerts.bellTitle')"
        @click="state.toggleAlerts()"
      >
        <template #icon>
          <span class="alert-bell-wrap">
            <Icon name="bell" :size="18" />
            <span v-if="alertTotal > 0" class="alert-bell-badge">
              <bdi>{{ alertTotal > 99 ? "99+" : alertTotal }}</bdi>
            </span>
          </span>
        </template>
      </Button>
      <LangToggle variant="header" />
    </template>

    <template #heading>
      <p class="fleet-page-eyebrow">{{ t("brand.eyebrow") }}</p>
      <h1 class="fleet-page-title">{{ t("brand.title") }}</h1>
      <p class="fleet-page-subtitle">{{ t("brand.subtitle") }}</p>
    </template>

    <div id="fleet-main" class="fleet-scene-body" tabindex="-1">
      <router-view />
    </div>
    </FleetPageShell>

    <AlertDrawer />

    <Dialog v-model="confirmOpen" :options="confirmOptions" @close="confirm.settle(false)">
      <template #body-content>
        <p class="cf-msg">{{ confirm.state.message }}</p>
      </template>
    </Dialog>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Button, Dialog, FrappeUIProvider, toast } from "frappe-ui";

import Brand from "@shared/components/Brand.vue";
import FleetPageShell from "@shared/components/FleetPageShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";

import Icon from "./Icon.vue";
import AlertDrawer from "./components/AlertDrawer.vue";
import { provideBoardContext } from "./boardContext.js";
import { useBoardState } from "./boardState.js";
import { provideConfirm } from "./confirm.js";
import { useDensity } from "./density.js";
import { connectFleetRealtime } from "./realtime.js";
import { useAlerts } from "./useAlerts.js";
import { useDriverAssignment } from "./useDriverAssignment.js";
import { useFleetActions } from "./useFleetActions.js";
import { useFleetBoard } from "./useFleetBoard.js";
import { useFleetFilters } from "./useFleetFilters.js";
import { useFleetFormat } from "./useFleetFormat.js";
import { useSelection } from "./useSelection.js";
import { useI18n } from "@/i18n";

const { t, lang, dir } = useI18n();
useDocumentLanguage(lang, dir);

const fmt = useFleetFormat(t);
const state = useBoardState();
const confirm = provideConfirm();
const { density, toggle: toggleDensity } = useDensity();

const TOAST_TYPES = { green: "success", amber: "warning", red: "error" };
function showToast(message, type = "green") {
  toast.create({
    message,
    type: TOAST_TYPES[type] || "info",
    duration: 3.5,
  });
}

const board = useFleetBoard({ expiryFlag: fmt.expiryFlag });
const { vehicles, loadState, reloadFleet } = board;

const filters = useFleetFilters({ vehicles, board: state, fmt, t });
const selection = useSelection(filters.filtered);

const panelVehicle = computed(
  () => vehicles.value.find((v) => v.plate === state.openPlate.value) || null,
);
const subForm = ref(null);
watch(
  () => state.openPlate.value,
  () => {
    subForm.value = null;
  },
);
watch(
  () => state.panelTab.value,
  () => {
    subForm.value = null;
  },
);

const assignment = useDriverAssignment({
  subForm,
  showToast,
  ask: confirm.ask,
  reloadFleet,
  panelVehicle,
  t,
});

const actions = useFleetActions({
  vehicles,
  openVehicle: state.openVehicle,
  subForm,
  showToast,
  ask: confirm.ask,
  reloadFleet,
  selected: selection.selected,
  clearSelection: selection.clearSelection,
  openReassignForm: assignment.openReassignForm,
  panelVehicle,
  t,
});

const alertsApi = useAlerts({
  vehicles,
  t,
  openVehicle: state.openVehicle,
  closeAlerts: () => state.setAlerts(false),
});
const { alertTotal, loadAlerts } = alertsApi;

const caps = (typeof window !== "undefined" && window.fleet_caps) || {};
const canDriverLens = computed(() => caps.driver_lens === true);

const confirmOpen = computed({
  get: () => confirm.state.open,
  set: (open) => {
    if (!open) confirm.settle(false);
  },
});
const confirmOptions = computed(() => ({
  title: confirm.state.title,
  size: "sm",
  actions: [
    {
      label: confirm.state.okLabel,
      variant: "solid",
      theme: confirm.state.theme,
      onClick: () => confirm.settle(true),
    },
    { label: t("common.cancel"), variant: "outline", onClick: () => confirm.settle(false) },
  ],
}));

provideBoardContext({
  t,
  fmt,
  state,
  board,
  filters,
  selection,
  actions,
  assignment,
  alerts: alertsApi,
  density,
  toggleDensity,
  canDriverLens,
  panelVehicle,
  subForm,
  showToast,
});

const POLL_MS = 30000;
const paused = computed(
  () =>
    loadState.value !== "ready" ||
    confirm.state.open ||
    Boolean(subForm.value) ||
    actions.busyPlates.value.size > 0 ||
    selection.selected.value.size > 0,
);

let pollTimer = null;
const realtimePending = ref(false);

async function refreshAll() {
  await reloadFleet();
  await loadAlerts();
}

async function tick() {
  if (document.hidden || paused.value) return;
  await refreshAll();
}

async function onRealtimeUpdate() {
  if (document.hidden || paused.value) {
    realtimePending.value = true;
    return;
  }
  realtimePending.value = false;
  await refreshAll();
}

watch(paused, (isPaused) => {
  if (!isPaused && realtimePending.value && !document.hidden) onRealtimeUpdate();
});

function onVisibility() {
  if (document.hidden) return;
  if (paused.value) realtimePending.value = true;
  else refreshAll();
}

let stopRealtime = () => {};
onMounted(() => {
  board.loadFleet();
  loadAlerts();
  pollTimer = setInterval(tick, POLL_MS);
  stopRealtime = connectFleetRealtime(onRealtimeUpdate);
  document.addEventListener("visibilitychange", onVisibility);
});
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  stopRealtime();
  document.removeEventListener("visibilitychange", onVisibility);
});
</script>
