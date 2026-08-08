<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div v-if="sheetOpen" class="fp-sheet-backdrop fp-mobile-only" aria-hidden="true" @click="sheetOpen = false"></div>

  <aside
    ref="sheetEl"
    class="sidebar"
    :class="{ 'fp-sheet-open': sheetOpen }"
    :role="isModal ? 'dialog' : null"
    :aria-modal="isModal ? 'true' : null"
    :aria-label="t('sidebar.filtersAndStats')"
  >
    <div class="sidebar-header">
      <span class="sidebar-title"><Icon name="funnel" :size="13" /> {{ t("sidebar.filtersAndStats") }}</span>
      <Button
        class="fp-mobile-only"
        variant="ghost"
        size="lg"
        :label="t('sidebar.close')"
        @click="sheetOpen = false"
      >
        <template #icon><Icon name="x" :size="16" /></template>
      </Button>
    </div>

    <div class="sidebar-scroll">
      <!-- Debounced so a search does not rewrite the address on every keystroke; the field is
           in the filter rail rather than the header because the header carries the page's
           identity and at most two actions, never a filter. -->
      <FormControl
        v-model="search"
        type="text"
        size="md"
        :debounce="250"
        :label="t('topbar.search')"
        :placeholder="t('topbar.searchPlaceholder')"
      >
        <template #prefix><Icon name="search" :size="15" /></template>
      </FormControl>

      <div class="fg">
        <div class="fl">{{ t("sidebar.vehicleType") }}</div>
        <TabButtons :buttons="typeButtons" :model-value="f.type.value" @update:model-value="setFilter('type', $event)" />
      </div>

      <FormControl
        type="select"
        size="md"
        :label="t('sidebar.project')"
        :options="allOption(projectOptions, t('sidebar.all'))"
        :model-value="f.project.value"
        :disabled="!projectOptions.length"
        @update:model-value="setFilter('project', $event)"
      />
      <FormControl
        type="select"
        size="md"
        :label="t('sidebar.area')"
        :options="allOption(areaOptions, t('sidebar.all'))"
        :model-value="f.area.value"
        :disabled="!areaOptions.length"
        @update:model-value="setFilter('area', $event)"
      />
      <FormControl
        type="select"
        size="md"
        :label="t('sidebar.rentalOffice')"
        :options="allOption(officeOptions, t('sidebar.all'))"
        :model-value="f.office.value"
        :disabled="!officeOptions.length"
        @update:model-value="setFilter('office', $event)"
      />

      <div class="fg">
        <div class="fl">{{ t("sidebar.fuel") }}</div>
        <TabButtons :buttons="fuelButtons" :model-value="f.fuel.value" @update:model-value="setFilter('fuel', $event)" />
      </div>

      <div class="sep"></div>

      <div class="fg">
        <div class="fl"><Icon name="calendar" :size="13" /> {{ t("sidebar.dateSearchType") }}</div>
        <TabButtons
          :buttons="dateTypeButtons"
          :model-value="f.dateType.value"
          @update:model-value="setFilter('dateType', $event)"
        />
      </div>

      <FormControl
        type="date"
        size="md"
        lang="en"
        :label="t('sidebar.dateFrom')"
        :model-value="f.from.value"
        @update:model-value="setFilter('from', $event)"
      />
      <FormControl
        type="date"
        size="md"
        lang="en"
        :label="t('sidebar.dateTo')"
        :model-value="f.to.value"
        @update:model-value="setFilter('to', $event)"
      />

      <div class="fg">
        <div class="fl">{{ t("sidebar.quickRange") }}</div>
        <div class="fchips">
          <Button v-for="r in ranges" :key="r.days" variant="outline" size="lg" :label="r.label" @click="setQuickDate(r.days)" />
          <Button variant="ghost" size="lg" :label="t('sidebar.clear')" @click="clearDates()" />
        </div>
      </div>

      <p v-if="hasDateFilter" class="fp-date-info">{{ dateInfo }}</p>

      <div class="sep"></div>
      <Button class="fp-block-btn" variant="outline" size="xl" :label="t('sidebar.reset')" @click="resetFilters()">
        <template #prefix><Icon name="rotate-cw" :size="15" /></template>
      </Button>

      <div class="sep"></div>
      <div class="fl"><Icon name="chart-column" :size="13" /> {{ t("sidebar.quickStats") }}</div>
      <div v-if="countsLoading" class="stat-mini-grid" aria-hidden="true">
        <div v-for="n in 7" :key="n" class="stat-mini fp-stat-skel"></div>
      </div>
      <div v-else class="stat-mini-grid">
        <div v-for="stat in stats" :key="stat.key" class="stat-mini">
          <div class="stat-mini-n">{{ stat.value }}</div>
          <div class="stat-mini-l">{{ stat.label }}</div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, FormControl, TabButtons } from "frappe-ui";

import { useMediaQuery } from "@shared/useBreakpoint.js";
import { useOverlay } from "@shared/useOverlay.js";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";
import { useFilterSheet } from "../filterSheet.js";

const { t, state, board, filters } = useBoardContext();
const { counts, countsLoading } = board;
const { projectOptions, areaOptions, officeOptions, dateInfo } = filters;
const { f, hasDateFilter, setFilter, setQuickDate, clearDates, resetFilters } = state;

const { sheetOpen } = useFilterSheet();
const sheetEl = ref(null);
/* Below the desktop breakpoint the rail becomes a sheet over the board, and a sheet over the
   board is a dialog: it traps the focus, Escape closes it, and focus returns to the button
   that opened it. */
const narrow = useMediaQuery("(max-width: 860px)");
const isModal = computed(() => sheetOpen.value && narrow.value);
useOverlay({ active: isModal, container: sheetEl, close: () => (sheetOpen.value = false) });

const search = computed({
  get: () => f.q.value,
  set: (value) => setFilter("q", value),
});

const allOption = (options, label) => [{ label, value: "" }, ...options];

const typeButtons = computed(() => [
  { label: t("sidebar.all"), value: "" },
  { label: t("sidebar.cars"), value: "CAR" },
  { label: t("sidebar.bikes"), value: "MOTORCYCLE" },
]);
const fuelButtons = computed(() => [
  { label: t("sidebar.all"), value: "" },
  { label: t("sidebar.petrol"), value: "PETROL" },
  { label: t("sidebar.diesel"), value: "DESIL" },
]);
const dateTypeButtons = computed(() => [
  { label: t("sidebar.receive"), value: "receive" },
  { label: t("sidebar.deliver"), value: "deliver" },
  { label: t("sidebar.anyDate"), value: "any" },
]);

const ranges = computed(() => [
  { days: 7, label: t("sidebar.days7") },
  { days: 30, label: t("sidebar.month1") },
  { days: 90, label: t("sidebar.months3") },
  { days: 180, label: t("sidebar.months6") },
  { days: 365, label: t("sidebar.year1") },
]);

const stats = computed(() => [
  { key: "total", value: counts.value.total, label: t("sidebar.total") },
  { key: "assigned", value: counts.value.assigned, label: t("sidebar.assigned") },
  { key: "available", value: counts.value.available, label: t("sidebar.available") },
  { key: "workshop", value: counts.value.workshop, label: t("sidebar.workshop") },
  { key: "stopped", value: counts.value.stopped, label: t("sidebar.stopped") },
  { key: "stolen", value: counts.value.stolen, label: t("sidebar.stolen") },
  { key: "drivers", value: counts.value.drivers, label: t("sidebar.drivers") },
]);
</script>
