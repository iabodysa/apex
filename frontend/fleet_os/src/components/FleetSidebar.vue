<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "f", "counts", "countsLoading", "hasDateFilter", "dateInfo",
  "filtersSheetOpen", "closeFiltersSheet",
  "projectOptions", "areaOptions", "officeOptions",
  "setSheet", "setFuel", "setDateType", "setQuickDate", "clearDateFilter", "resetFilters", "t",
]);
</script>

<template>
    <div v-if="filtersSheetOpen" class="fp-sheet-backdrop fp-mobile-only" aria-hidden="true" @click="closeFiltersSheet"></div>
    <div class="sidebar" :class="{ 'fp-sheet-open': filtersSheetOpen }">
      <div class="sidebar-header">
        <span class="sidebar-title"><Icon name="funnel" :size="13" /> {{ t("sidebar.filtersAndStats") }}</span>
        <button class="panel-close fp-sheet-close fp-mobile-only" :aria-label="t('sidebar.close')" @click="closeFiltersSheet"><Icon name="x" :size="16" /></button>
      </div>
      <div class="sidebar-scroll">
        <div class="fg">
          <div class="fl">{{ t("sidebar.vehicleType") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.sheet === '' }" @click="setSheet('')">{{ t("sidebar.all") }}</button>
            <button class="fchip" :class="{ on: f.sheet === 'CAR' }" @click="setSheet('CAR')"><Icon name="car" :size="15" /> {{ t("sidebar.cars") }}</button>
            <button class="fchip" :class="{ on: f.sheet === 'MOTORCYCLE' }" @click="setSheet('MOTORCYCLE')"><Icon name="bike" :size="15" /> {{ t("sidebar.bikes") }}</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.project") }}</div>
          <select class="fs" v-model="f.project" :disabled="!projectOptions.length">
            <option value="">{{ t("sidebar.all") }}</option>
            <option v-for="o in projectOptions" :key="o">{{ o }}</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.area") }}</div>
          <select class="fs" v-model="f.area" :disabled="!areaOptions.length">
            <option value="">{{ t("sidebar.all") }}</option>
            <option v-for="o in areaOptions" :key="o">{{ o }}</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.rentalOffice") }}</div>
          <select class="fs" v-model="f.office" :disabled="!officeOptions.length">
            <option value="">{{ t("sidebar.all") }}</option>
            <option v-for="o in officeOptions" :key="o">{{ o }}</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.fuel") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.fuel === '' }" @click="setFuel('')">{{ t("sidebar.all") }}</button>
            <button class="fchip" :class="{ on: f.fuel === 'PETROL' }" @click="setFuel('PETROL')"><Icon name="fuel" :size="15" /> {{ t("sidebar.petrol") }}</button>
            <button class="fchip" :class="{ on: f.fuel === 'DESIL' }" @click="setFuel('DESIL')"><Icon name="fuel" :size="15" /> {{ t("sidebar.diesel") }}</button>
          </div>
        </div>
        <div class="sep"></div>
        <div class="fg">
          <div class="fl"><Icon name="calendar" :size="13" /> {{ t("sidebar.dateSearchType") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.dateType === 'receive' }" @click="setDateType('receive')">{{ t("sidebar.receive") }}</button>
            <button class="fchip" :class="{ on: f.dateType === 'deliver' }" @click="setDateType('deliver')">{{ t("sidebar.deliver") }}</button>
            <button class="fchip" :class="{ on: f.dateType === 'any' }" @click="setDateType('any')">{{ t("sidebar.anyDate") }}</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.dateFrom") }}</div>
          <input type="date" class="fs" v-model="f.dateFrom" />
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.dateTo") }}</div>
          <input type="date" class="fs" v-model="f.dateTo" />
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.quickRange") }}</div>
          <div class="fchips" style="flex-wrap:wrap">
            <button class="fchip" @click="setQuickDate(7)">{{ t("sidebar.days7") }}</button>
            <button class="fchip" @click="setQuickDate(30)">{{ t("sidebar.month1") }}</button>
            <button class="fchip" @click="setQuickDate(90)">{{ t("sidebar.months3") }}</button>
            <button class="fchip" @click="setQuickDate(180)">{{ t("sidebar.months6") }}</button>
            <button class="fchip" @click="setQuickDate(365)">{{ t("sidebar.year1") }}</button>
            <button class="fchip" @click="clearDateFilter">{{ t("sidebar.clear") }}</button>
          </div>
        </div>
        <div v-if="hasDateFilter" style="font-size:10px;color:var(--t3);padding:4px 0">{{ dateInfo }}</div>
        <div class="sep"></div>
        <button class="btn" style="width:100%;justify-content:center" @click="resetFilters"><Icon name="rotate-cw" :size="15" /> {{ t("sidebar.reset") }}</button>
        <div class="sep"></div>
        <div class="fl" style="margin-bottom:8px"><Icon name="chart-column" :size="13" /> {{ t("sidebar.quickStats") }}</div>
        <div v-if="countsLoading" class="stat-mini-grid">
          <div class="stat-mini fp-stat-skel" v-for="n in 7" :key="n"></div>
        </div>
        <div v-else class="stat-mini-grid">
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.total }}</div><div class="stat-mini-l">{{ t("sidebar.total") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--green-l)">{{ counts.assigned }}</div><div class="stat-mini-l">{{ t("sidebar.assigned") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--cyan-l)">{{ counts.available }}</div><div class="stat-mini-l">{{ t("sidebar.available") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--orange-l)">{{ counts.workshop }}</div><div class="stat-mini-l">{{ t("sidebar.workshop") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--t3)">{{ counts.stopped }}</div><div class="stat-mini-l">{{ t("sidebar.stopped") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--purple-l)">{{ counts.stolen }}</div><div class="stat-mini-l">{{ t("sidebar.stolen") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.drivers }}</div><div class="stat-mini-l">{{ t("sidebar.drivers") }}</div></div>
        </div>
      </div>
    </div>
</template>
