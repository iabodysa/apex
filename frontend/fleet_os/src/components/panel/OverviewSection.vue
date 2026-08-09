<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <h3 class="psect-title"><Icon name="chart-column" :size="14" /> {{ t("panel.vehicleStats") }}</h3>
  <MetricRibbon :metrics="stats" />

  <h3 class="psect-title"><Icon name="car" :size="14" /> {{ t("panel.vehicleDetails") }}</h3>
  <dl class="kv-grid">
    <div v-for="row in details" :key="row.label" class="kv">
      <dt class="kv-l">{{ row.label }}</dt>
      <dd class="kv-v" :class="{ mono: row.mono }">
        <bdi v-if="row.mono">{{ row.value }}</bdi>
        <template v-else>{{ row.value }}</template>
      </dd>
    </div>
  </dl>

  <h3 class="psect-title"><Icon name="fuel" :size="14" /> {{ t("panel.fuelPlan") }}</h3>
  <!-- Grade and the planned daily figure, both from the vehicle's own record. The per-litre
       price that used to sit here was fixed in the bundle and rendered as if it had come from
       the server, and the "monthly" figure beside it was the daily one times a flat 30. -->
  <div class="fuel-row">
    <Badge theme="orange" size="md" :label="fuel.gradeLabel" />
    <span v-if="fuel.daily > 0" class="fuel-daily">
      <b><bdi>{{ fuel.dailyDisplay }}</bdi></b> {{ t("panel.plannedDaily") }}
    </span>
    <span v-else class="fuel-daily">{{ t("panel.noFuelPlan") }}</span>
  </div>

  <template v-if="vehicle.current_driver">
    <h3 class="psect-title"><Icon name="user" :size="14" /> {{ t("panel.currentDriver") }}</h3>
    <div class="cur-driver-card">
      <span class="cdc-av">{{ fmt.initials(vehicle.current_driver) }}</span>
      <div class="cdc-info">
        <div class="cdc-name">
          {{ vehicle.current_driver.name_ar || vehicle.current_driver.name_en || t("common.none") }}
        </div>
        <div class="cdc-en">{{ vehicle.current_driver.name_en || "" }}</div>
        <div class="cdc-chips">
          <span class="cdc-chip"><Icon name="phone" :size="11" /> <bdi>{{ vehicle.current_driver.mobile || t("common.none") }}</bdi></span>
          <span class="cdc-chip"><Icon name="id-card" :size="11" /> <bdi>{{ vehicle.current_driver.driver_id || t("common.none") }}</bdi></span>
          <span class="cdc-chip"><Icon name="calendar" :size="11" /> <bdi>{{ vehicle.current_driver.date_receive || t("common.none") }}</bdi></span>
        </div>
      </div>
      <Badge theme="green" size="md" :label="t('panel.active')" />
    </div>
  </template>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";

import MetricRibbon from "@shared/components/MetricRibbon.vue";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
});

const { t, fmt } = useBoardContext();

const fuel = computed(() => fmt.fuelView(props.vehicle));

const stats = computed(() => [
  { key: "drivers", value: props.vehicle.history.length, label: t("panel.totalDrivers") },
  { key: "running", value: fmt.calcTotalDaysNum(props.vehicle), label: t("panel.runningDays") },
  { key: "active", value: fmt.calcActiveDaysNum(props.vehicle), label: t("panel.activeDays") },
  {
    key: "activations",
    value: props.vehicle.history.filter((h) => h.status === "Active").length,
    label: t("panel.activations"),
  },
]);

const details = computed(() => [
  { label: t("panel.plate"), value: props.vehicle.plate, mono: true },
  {
    label: t("panel.type"),
    value: props.vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike"),
  },
  { label: t("panel.model"), value: props.vehicle.vehicle_type || t("common.none") },
  { label: t("panel.fuel"), value: props.vehicle.fuel || t("common.none") },
  { label: t("panel.rentalOffice"), value: props.vehicle.rental_office || t("common.none") },
  { label: t("panel.area"), value: props.vehicle.area || t("common.none") },
  { label: t("panel.project"), value: fmt.trim(props.vehicle.project) || t("common.none") },
  { label: t("panel.vehicleStatus"), value: fmt.sb(props.vehicle).label },
]);
</script>
