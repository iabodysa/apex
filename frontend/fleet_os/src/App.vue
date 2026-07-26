<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * Fleet OS supervisor board — a thin shell that composes the board's concerns
 * (data, filters, selection, panel, alerts, actions) from src/use*.js and lays
 * out the presentational components in src/components/. The original ~1900-line
 * god component was split here with zero behavior change; each concern now lives
 * in its own cohesive composable/component.
 *
 * The live-sync lifecycle (poll + realtime) is orchestrated in THIS shell because
 * its pause guard must read confirm/panel/selection/action state — genuine
 * top-level wiring that can't live inside any one composable without a cycle.
 */
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
// Direct-path import (documented + supported): the @shared/components barrel also
// re-exports BuildingPicker, which needs a portal i18n export the Fleet portal
// doesn't provide, so importing the shell file directly keeps the bundle clean.
import FleetPageShell from "@shared/components/FleetPageShell.vue";
import { connectFleetRealtime } from "./realtime.js";
import Icon from "./components/Icon.vue";
import LangToggle from "./components/LangToggle.vue";
import FleetSidebar from "./components/FleetSidebar.vue";
import FleetToolbar from "./components/FleetToolbar.vue";
import FleetCardGrid from "./components/FleetCardGrid.vue";
import FleetDriverLens from "./components/FleetDriverLens.vue";
import FleetTable from "./components/FleetTable.vue";
import AlertDrawer from "./components/AlertDrawer.vue";
import VehiclePanel from "./components/VehiclePanel.vue";
import { useI18n } from "./i18n";
import { useFleetFormat } from "./useFleetFormat.js";
import { useToast } from "@shared/useToast.js";
import { useConfirm } from "./useConfirm.js";
import { useFleetBoard } from "./useFleetBoard.js";
import { useVehiclePanel } from "./useVehiclePanel.js";
import { useAlerts } from "./useAlerts.js";
import { useFleetFilters } from "./useFleetFilters.js";
import { useSelection } from "./useSelection.js";
import { useDriverAssignment } from "./useDriverAssignment.js";
import { useFleetActions } from "./useFleetActions.js";

const { t, dir } = useI18n();

// Keep the document direction/lang in sync so native RTL applies page-wide.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// Display formatters (single source: pure helpers + t-bound ones).
const fmt = useFleetFormat(t);

// Board data model (vehicles + counts + triage).
const board = useFleetBoard({ expiryFlag: fmt.expiryFlag });
const {
  vehicles, loadState, loadError, reloadStale, isScopeEmpty,
  counts, countsLoading, triage, loadFleet,
} = board;

// Toast + promise-based confirm.
const { toast, showToast } = useToast();
const { cf, cfShow, cfDo } = useConfirm(t);

// Detail drawer.
const { panel, subForm, openPanel, closePanel, setPTab, tabDmg, tabAcc } = useVehiclePanel(vehicles);
// Cancel-buttons close the open sub-form (a ref write kept out of child templates).
function closeSubForm() {
  subForm.value = null;
}

// Operations alerts (bell + drawer).
const {
  alerts, alertTotal, alertsState, alertsOpen,
  loadAlerts, toggleAlerts, closeAlerts,
  sevClass, sevLabel, alertVehicleOnBoard, openAlertTarget,
} = useAlerts({ vehicles, t, openPanel });

// Background re-pull wrapper: board fetch + re-point the open panel to the fresh
// row (or close it if the vehicle left the scoped list).
async function reloadFleet() {
  await board.reloadFleet();
  if (panel.open && panel.plate) {
    const fresh = vehicles.value.find((x) => x.plate === panel.plate);
    if (fresh) panel.vehicle = fresh;
    else closePanel();
  }
}

// Filters / sort / view + derived lists.
const {
  f, triageFilter,
  setSP, setSheet, setFuel, setDateType, setView, setTriage, onSortCol,
  setQuickDate, clearDateFilter, resetFilters,
  hasDateFilter, anyFilterActive, filtered, driverGroups, dateInfo, activeFilterChips,
  density, toggleDensity,
  filtersSheetOpen, toggleFiltersSheet, closeFiltersSheet,
} = useFleetFilters({ vehicles, fmt, t });

// Multi-select (bulk actions).
const {
  selectMode, selected, selectedCount, isSelected,
  toggleSelect, clearSelection, toggleSelectMode,
  allVisibleSelected, toggleSelectAll,
} = useSelection(filtered);

// Assign/reassign flow (driver picker + optional handover).
const {
  rf, dp, onDriverQuery, pickDriver,
  openReassignForm, openNewDriverForm, submitReassign,
} = useDriverAssignment({ panel, subForm, showToast, cfShow, reloadFleet, t });

// Status / quick / bulk actions.
const {
  busyPlates, isBusy,
  sf, openStopForm, confirmStop,
  stf, openStolenForm, submitStolen,
  quickStop, quickReassign, sendWorkshop, exitWorkshop, setAvailable, recoverVehicle, markStolen,
  bulkNote, bulkStop, bulkWorkshop,
  changeStatus,
} = useFleetActions({
  vehicles, panel, subForm, openPanel,
  showToast, cfShow, reloadFleet,
  selected, clearSelection, openReassignForm, t,
});

// Driver-centric lens: shown only when the server grants the capability flag.
const caps = (typeof window !== "undefined" && window.fleet_caps) || {};
const canDriverLens = computed(() => caps.driver_lens === true);

// ═══════════ LIVE SYNC (poll + realtime) ═══════════
// Paused while the tab is hidden, the first load hasn't landed, or the user is
// mid-interaction (a write in flight, a sub-form/confirm open, or a selection
// active) so a tick can't clobber their state.
const POLL_MS = 30000;
let pollTimer = null;
const pollPaused = computed(
  () =>
    loadState.value !== "ready" ||
    cf.open ||
    !!subForm.value ||
    busyPlates.value.size > 0 ||
    selected.value.size > 0
);
async function pollTick() {
  if (document.hidden || pollPaused.value) return;
  await reloadFleet();
  await loadAlerts();
}
function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(pollTick, POLL_MS);
}
function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
// Realtime socket push, ahead of the poll. A push that lands mid-interaction is
// deferred via a pending flag, then flushed the moment the user is free.
let stopRealtime = () => {};
const realtimePending = ref(false);
async function onRealtimeUpdate() {
  if (document.hidden || pollPaused.value) {
    realtimePending.value = true;
    return;
  }
  realtimePending.value = false;
  await reloadFleet();
  await loadAlerts();
}
watch(pollPaused, (paused) => {
  if (!paused && realtimePending.value && !document.hidden) onRealtimeUpdate();
});
// Re-sync immediately when the tab regains focus, then keep polling.
function onVisibility() {
  if (document.hidden) return;
  if (!pollPaused.value) reloadFleet();
  else realtimePending.value = true; // flush the missed update once free
}
onMounted(() => {
  loadFleet();
  loadAlerts();
  startPoll();
  stopRealtime = connectFleetRealtime(onRealtimeUpdate);
  document.addEventListener("visibilitychange", onVisibility);
});
onUnmounted(() => {
  stopPoll();
  stopRealtime();
  document.removeEventListener("visibilitychange", onVisibility);
});
</script>

<template>
  <FleetPageShell max-width="100%">
    <template #brand>
      <span class="fp-brandmark"><Icon name="car" :size="20" /></span>
      <span class="fp-brandword">{{ t("brand.name") }}</span>
    </template>
    <template #actions>
      <div class="search-bar fp-head-search">
        <span class="si"><Icon name="search" :size="15" /></span>
        <input v-model="f.search" :placeholder="t('topbar.searchPlaceholder')" />
      </div>
      <button class="alert-bell" :class="{ active: alertsOpen }" :title="t('alerts.bellTitle')" :aria-label="t('alerts.bellTitle')" @click="toggleAlerts">
        <Icon name="bell" :size="18" />
        <span v-if="alertTotal > 0" class="alert-bell-badge">{{ alertTotal > 99 ? "99+" : alertTotal }}</span>
      </button>
      <LangToggle />
    </template>

    <!-- STATUS / KPI / TRIAGE PILLS (shimmer until the first load resolves) -->
    <div class="fp-pills-bar">
      <template v-if="countsLoading">
        <span v-for="n in 6" :key="n" class="sp fp-kpi-skel"></span>
      </template>
      <template v-else>
        <span class="sp sp-all" :class="{ active: f.status === '' }" @click="setSP('')">{{ counts.total }} {{ t("topbar.allVehicles") }}</span>
        <span class="sp sp-assigned" :class="{ active: f.status === 'assigned' }" @click="setSP('assigned')">{{ counts.assigned }} {{ t("statusShort.assigned") }}</span>
        <span class="sp sp-available" :class="{ active: f.status === 'available' }" @click="setSP('available')">{{ counts.available }} {{ t("statusShort.available") }}</span>
        <span class="sp sp-workshop" :class="{ active: f.status === 'workshop' }" @click="setSP('workshop')">{{ counts.workshop }} {{ t("statusShort.workshop") }}</span>
        <span class="sp sp-stopped" :class="{ active: f.status === 'stopped' }" @click="setSP('stopped')">{{ counts.stopped }} {{ t("statusShort.stopped") }}</span>
        <span class="sp sp-stolen" :class="{ active: f.status === 'stolen' }" @click="setSP('stolen')">{{ counts.stolen }} {{ t("statusShort.stolen") }}</span>
        <span v-if="triage.incidents" class="sp sp-triage-incident" :class="{ active: triageFilter === 'incidents' }" @click="setTriage('incidents')"><Icon name="crash" :size="12" /> {{ triage.incidents }} {{ t("topbar.openIncidents") }}</span>
        <span v-if="triage.expiring" class="sp sp-triage-expiry" :class="{ active: triageFilter === 'expiring' }" @click="setTriage('expiring')"><Icon name="shield-alert" :size="12" /> {{ triage.expiring }} {{ t("topbar.expiringSoon") }}</span>
      </template>
    </div>

    <div class="layout">
    <FleetSidebar
      :f="f" :counts="counts" :countsLoading="countsLoading" :hasDateFilter="hasDateFilter"
      :dateInfo="dateInfo" :filtersSheetOpen="filtersSheetOpen" :closeFiltersSheet="closeFiltersSheet"
      :setSheet="setSheet" :setFuel="setFuel" :setDateType="setDateType" :setQuickDate="setQuickDate"
      :clearDateFilter="clearDateFilter" :resetFilters="resetFilters" :t="t"
    />

    <div class="main">
      <FleetToolbar
        :f="f" :filtered="filtered" :anyFilterActive="anyFilterActive" :selectMode="selectMode"
        :density="density" :canDriverLens="canDriverLens" :toggleFiltersSheet="toggleFiltersSheet"
        :toggleSelectMode="toggleSelectMode" :setView="setView" :toggleDensity="toggleDensity" :t="t"
      />

      <!-- BULK ACTION BAR: kept in the shell (bulkNote is a bare ref v-model) -->
      <div v-if="selectMode && selectedCount" class="fp-bulk-bar">
        <span class="fp-bulk-count">{{ t("bulk.selected", { n: selectedCount }) }}</span>
        <input class="fp-bulk-note fs" v-model="bulkNote" :placeholder="t('stopForm.notesPlaceholder')" />
        <div class="fp-bulk-actions">
          <button class="btn btn-red" @click="bulkStop"><Icon name="circle-pause" :size="14" /> {{ t("bulk.stopSelected") }}</button>
          <button class="btn btn-amber" @click="bulkWorkshop"><Icon name="wrench" :size="14" /> {{ t("bulk.workshopSelected") }}</button>
          <button class="btn" @click="clearSelection"><Icon name="x" :size="14" /> {{ t("bulk.clear") }}</button>
        </div>
      </div>

      <!-- STALE (background refresh failed; the last good board is still shown) -->
      <div v-if="loadState === 'ready' && reloadStale" class="fp-error-banner" style="border-color:var(--amber);background:color-mix(in srgb,var(--amber) 12%,transparent)">
        <span style="color:var(--amber)"><Icon name="triangle-alert" :size="20" /></span>
        <span class="fp-err-msg">{{ t("main.staleData") }}</span>
        <button class="btn btn-amber" @click="reloadFleet">{{ t("common.retry") }}</button>
      </div>

      <!-- ERROR (persistent banner + retry) -->
      <div v-if="loadState === 'error'" class="fp-error-banner">
        <span style="color:var(--red-l)"><Icon name="triangle-alert" :size="20" /></span>
        <span class="fp-err-msg">{{ t("main.loadError", { error: loadError }) }}</span>
        <button class="btn btn-red" @click="loadFleet">{{ t("common.retry") }}</button>
      </div>

      <!-- LOADING (skeleton) -->
      <div v-else-if="loadState === 'loading'" class="cards-wrap">
        <div class="cards-grid">
          <div class="fp-skel-card" v-for="n in 8" :key="n">
            <div class="fp-skel-line" style="width:40%"></div>
            <div class="fp-skel-line" style="width:70%"></div>
            <div class="fp-skel-line" style="width:55%"></div>
            <div class="fp-skel-line" style="width:80%"></div>
          </div>
        </div>
      </div>

      <FleetCardGrid
        v-else-if="f.view === 'cards'"
        :filtered="filtered" :density="density" :isScopeEmpty="isScopeEmpty"
        :anyFilterActive="anyFilterActive" :activeFilterChips="activeFilterChips"
        :selectMode="selectMode" :resetFilters="resetFilters" :isSelected="isSelected"
        :toggleSelect="toggleSelect" :isBusy="isBusy" :openPanel="openPanel"
        :sb="fmt.sb" :icon="fmt.icon" :trim="fmt.trim" :initials="fmt.initials"
        :expiryFlag="fmt.expiryFlag" :calcTotalDaysNum="fmt.calcTotalDaysNum"
        :quickStop="quickStop" :quickReassign="quickReassign" :sendWorkshop="sendWorkshop"
        :exitWorkshop="exitWorkshop" :setAvailable="setAvailable" :recoverVehicle="recoverVehicle"
        :markStolen="markStolen" :t="t"
      />

      <FleetDriverLens
        v-else-if="f.view === 'drivers'"
        :filtered="filtered" :isScopeEmpty="isScopeEmpty" :anyFilterActive="anyFilterActive"
        :resetFilters="resetFilters" :driverGroups="driverGroups"
        :initials="fmt.initials" :icon="fmt.icon" :sb="fmt.sb" :sl="fmt.sl" :trim="fmt.trim"
        :openPanel="openPanel" :t="t"
      />

      <FleetTable
        v-else
        :filtered="filtered" :isScopeEmpty="isScopeEmpty" :selectMode="selectMode"
        :allVisibleSelected="allVisibleSelected" :toggleSelectAll="toggleSelectAll"
        :isSelected="isSelected" :toggleSelect="toggleSelect" :onSortCol="onSortCol"
        :openPanel="openPanel" :icon="fmt.icon" :sb="fmt.sb" :sl="fmt.sl" :trim="fmt.trim"
        :calcTotalDaysNum="fmt.calcTotalDaysNum" :t="t"
      />
    </div>
    </div>
  </FleetPageShell>

  <AlertDrawer
    :alertsOpen="alertsOpen" :alertsState="alertsState" :alerts="alerts" :alertTotal="alertTotal"
    :closeAlerts="closeAlerts" :sevClass="sevClass" :sevLabel="sevLabel"
    :alertVehicleOnBoard="alertVehicleOnBoard" :openAlertTarget="openAlertTarget" :t="t"
  />

  <VehiclePanel
    :panel="panel" :subForm="subForm" :closePanel="closePanel" :setPTab="setPTab"
    :tabDmg="tabDmg" :tabAcc="tabAcc" :closeSubForm="closeSubForm"
    :sb="fmt.sb" :initials="fmt.initials" :calcTotalDaysNum="fmt.calcTotalDaysNum"
    :calcActiveDaysNum="fmt.calcActiveDaysNum" :fuelView="fmt.fuelView" :trim="fmt.trim"
    :historyItems="fmt.historyItems" :calcDur="fmt.calcDur" :today="fmt.today"
    :openStopForm="openStopForm" :openReassignForm="openReassignForm" :sf="sf" :confirmStop="confirmStop"
    :dp="dp" :onDriverQuery="onDriverQuery" :pickDriver="pickDriver"
    :openNewDriverForm="openNewDriverForm" :rf="rf" :submitReassign="submitReassign"
    :changeStatus="changeStatus" :stf="stf" :submitStolen="submitStolen"
    :openStolenForm="openStolenForm" :recoverVehicle="recoverVehicle" :t="t"
  />

  <!-- TOAST -->
  <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>

  <!-- CUSTOM CONFIRM MODAL -->
  <div v-if="cf.open" class="cf-overlay" @click.self="cfDo(false)">
    <div class="cf-box">
      <div class="cf-icon"><Icon :name="cf.icon" :size="36" :stroke-width="1.75" /></div>
      <div class="cf-title">{{ cf.title }}</div>
      <div class="cf-msg">{{ cf.msg }}</div>
      <div class="cf-btns">
        <button class="btn" @click="cfDo(false)">{{ t("common.cancel") }}</button>
        <button class="btn" :class="cf.okCls" @click="cfDo(true)">{{ cf.okLabel }}</button>
      </div>
    </div>
  </div>
</template>
