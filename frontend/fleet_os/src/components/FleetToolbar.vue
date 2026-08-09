<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <header class="ledger-toolbar">
    <div class="ledger-heading">
      <p>{{ t("main.workingSetEyebrow") }}</p>
      <h2>{{ t("main.workingSet") }}</h2>
      <span class="result-count"><bdi>{{ filtered.length }}</bdi> {{ t("main.vehiclesLabel") }}</span>
    </div>

    <div class="ledger-controls">
      <Button
        class="fp-mobile-only"
        :variant="anyFilterActive ? 'solid' : 'outline'"
        :theme="anyFilterActive ? 'green' : 'gray'"
        size="xl"
        :label="t('sidebar.filters')"
        @click="sheetOpen = true"
      >
        <template #prefix><Icon name="funnel" :size="14" /></template>
      </Button>

      <FormControl
        class="ledger-sort"
        type="select"
        size="md"
        :label="t('main.sortLabel')"
        :options="sortOptions"
        :model-value="sort"
        @update:model-value="setSort($event)"
      />
      <Button
        :variant="selectMode ? 'solid' : 'outline'"
        :theme="selectMode ? 'green' : 'gray'"
        size="xl"
        :label="t('bulk.selectVehicles')"
        @click="toggleSelectMode()"
      >
        <template #prefix><Icon name="circle-check" :size="14" /></template>
      </Button>

      <Button
        v-if="view === 'cards'"
        variant="outline"
        size="xl"
        :label="density === 'compact' ? t('main.comfortable') : t('main.compact')"
        :tooltip="t('main.densityTitle')"
        @click="toggleDensity()"
      >
        <template #prefix><Icon :name="density === 'compact' ? 'list' : 'layout-grid'" :size="14" /></template>
      </Button>

      <TabButtons :buttons="viewButtons" :model-value="view" @update:model-value="setView($event)" />
    </div>
  </header>
</template>

<script setup>
import { computed } from "vue";
import { Button, FormControl, TabButtons } from "frappe-ui";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";
import { useFilterSheet } from "../filterSheet.js";

const { t, state, filters, selection, density, toggleDensity, canDriverLens } = useBoardContext();
const { sort, view, anyFilterActive, setSort, setView } = state;
const { filtered } = filters;
const { selectMode, toggleSelectMode } = selection;
const { sheetOpen } = useFilterSheet();

/* One control writes the sort, and it writes the address. The board used to keep the sort in
   two places — a `sort` value the list read and a `sortCol` the table headers read — so
   clearing the filters reset one and left the other, and the next header click started
   descending. */
const sortOptions = computed(() => [
  { label: t("main.sortPlate"), value: "plate" },
  { label: t("main.sortStatus"), value: "status" },
  { label: t("main.sortType"), value: "vehicle_type" },
  { label: t("table.colType"), value: "sheet" },
  { label: t("table.colOffice"), value: "rental_office" },
  { label: t("table.colProject"), value: "project" },
  { label: t("table.colArea"), value: "area" },
  { label: t("main.sortMostDrivers"), value: "drivers_desc" },
  { label: t("main.sortLongestRunning"), value: "duration_desc" },
]);

const viewButtons = computed(() => {
  const buttons = [
    { label: t("main.cards"), value: "cards" },
    { label: t("main.table"), value: "table" },
  ];
  if (canDriverLens.value) {
    buttons.push({ label: t("main.drivers"), value: "drivers", tooltip: t("main.driversTitle") });
  }
  return buttons;
});
</script>
