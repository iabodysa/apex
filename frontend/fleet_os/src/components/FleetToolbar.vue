<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Main header: result count, sort, select-mode, density, and the view tabs. -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "f", "filtered", "anyFilterActive", "selectMode", "density", "canDriverLens",
  "toggleFiltersSheet", "toggleSelectMode", "setView", "toggleDensity", "t",
]);
</script>

<template>
      <div class="main-header">
        <div style="display:flex;align-items:center;gap:10px">
          <!-- Mobile-only: opens the filters/stats bottom sheet (sidebar is hidden on phones) -->
          <button class="btn fp-filters-btn fp-mobile-only" :class="{ 'btn-blue': anyFilterActive }" @click="toggleFiltersSheet"><Icon name="funnel" :size="14" /> {{ t("sidebar.filters") }}<span v-if="anyFilterActive" class="fp-filters-dot"></span></button>
          <span class="rcount">{{ t("main.vehicleCount", { n: filtered.length }) }}</span>
          <select class="fs" style="width:auto;font-size:11px" v-model="f.sort">
            <option value="plate">{{ t("main.sortBy", { field: t("main.sortPlate") }) }}</option>
            <option value="status">{{ t("main.sortBy", { field: t("main.sortStatus") }) }}</option>
            <option value="vehicle_type">{{ t("main.sortBy", { field: t("main.sortType") }) }}</option>
            <option value="sheet">{{ t("main.sortBy", { field: t("table.colType") }) }}</option>
            <option value="rental_office">{{ t("main.sortBy", { field: t("table.colOffice") }) }}</option>
            <option value="project">{{ t("main.sortBy", { field: t("table.colProject") }) }}</option>
            <option value="area">{{ t("main.sortBy", { field: t("table.colArea") }) }}</option>
            <option value="drivers_desc">{{ t("main.sortBy", { field: t("main.sortMostDrivers") }) }}</option>
            <option value="duration_desc">{{ t("main.sortBy", { field: t("main.sortLongestRunning") }) }}</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <button class="btn" :class="{ 'btn-blue': selectMode }" @click="toggleSelectMode"><Icon name="circle-check" :size="14" /> {{ t("bulk.selectVehicles") }}</button>
          <button v-if="f.view === 'cards'" class="btn" :class="{ 'btn-blue': density === 'compact' }" :title="t('main.densityTitle')" @click="toggleDensity"><Icon :name="density === 'compact' ? 'list' : 'layout-grid'" :size="14" /> {{ density === 'compact' ? t("main.comfortable") : t("main.compact") }}</button>
          <div class="view-tabs">
            <button class="vt" :class="{ on: f.view === 'cards' }" @click="setView('cards')"><Icon name="layout-grid" :size="14" /> {{ t("main.cards") }}</button>
            <button class="vt" :class="{ on: f.view === 'table' }" @click="setView('table')"><Icon name="list" :size="14" /> {{ t("main.table") }}</button>
            <!-- Driver-centric lens: shown only when the server grants the capability -->
            <button v-if="canDriverLens" class="vt" :class="{ on: f.view === 'drivers' }" :title="t('main.driversTitle')" @click="setView('drivers')"><Icon name="user" :size="14" /> {{ t("main.drivers") }}</button>
          </div>
        </div>
      </div>
</template>
