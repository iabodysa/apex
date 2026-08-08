<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <FleetPageShell max-width="100%">
    <template #brand>
      <span class="fp-brandmark"><Icon name="car" :size="20" /></span>
      <span class="fp-brandword">{{ t("brand.name") }}</span>
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
              {{ alertTotal > 99 ? "99+" : alertTotal }}
            </span>
          </span>
        </template>
      </Button>
      <LangToggle variant="header" />
    </template>

    <router-view />
  </FleetPageShell>

  <VehiclePanel />
  <AlertDrawer />

  <Dialog v-model="confirmOpen" :options="confirmOptions" @close="confirm.settle(false)">
    <template #body-content>
      <p class="cf-msg">{{ confirm.state.message }}</p>
    </template>
  </Dialog>

  <PortalToast :toast="toast" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Button, Dialog } from "frappe-ui";

import FleetPageShell from "@shared/components/FleetPageShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { useToast } from "@shared/useToast.js";

import Icon from "./Icon.vue";
import AlertDrawer from "./components/AlertDrawer.vue";
import PortalToast from "./components/PortalToast.vue";
import VehiclePanel from "./components/VehiclePanel.vue";
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
const { toast, showToast } = useToast();
const confirm = provideConfirm();
const { density, toggle: toggleDensity } = useDensity();

const board = useFleetBoard({ expiryFlag: fmt.expiryFlag });
const { vehicles, loadState, reloadFleet } = board;

const filters = useFleetFilters({ vehicles, board: state, fmt, t });
const selection = useSelection(filters.filtered);

/* The open vehicle is derived from the address and the freshly loaded board, so a reload keeps
   the panel showing current data and a vehicle that leaves the board closes its own panel. */
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

/* One capability arrives from the page: whether the driver lens is offered. It is a display
   gate — the rows behind it come down in get_fleet_os regardless — and the server decides it,
   so it is read exactly as published rather than assumed. */
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

/* The board refuses to repaint under the supervisor's hands. All five conditions are behaviour
   earned by real breakage: never while the first load is still running, never while a
   confirmation is open, never while a sub-form is half typed, never while a per-vehicle action
   is in flight, and never while anything is selected. */
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

/* An update that arrives during a pause is remembered and replayed the moment the pause lifts,
   rather than dropped — the supervisor finishes his action and then sees the newer board. */
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
