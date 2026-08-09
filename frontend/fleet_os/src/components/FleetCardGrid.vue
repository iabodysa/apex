<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <EmptyBoard v-if="!filtered.length" icon="car" />

  <div v-else class="scan-grid" :class="{ 'is-compact': density === 'compact' }">
    <article
      v-for="v in filtered"
      :key="v.plate"
      class="scan-record"
      :class="{ 'is-selected': selectMode && isSelected(v.plate), 'is-busy': isBusy(v.plate) }"
    >
      <header class="scan-record-head">
        <Checkbox
          v-if="selectMode"
          :model-value="isSelected(v.plate)"
          :disabled="selectionLimitReached && !isSelected(v.plate)"
          :label="t('bulk.selectOne', { plate: v.plate })"
          @update:model-value="toggleSelect(v.plate)"
        />
        <button type="button" class="scan-identity" @click="openVehicle(v.plate)">
          <Icon :name="fmt.icon(v)" :size="21" />
          <bdi class="mono scan-plate">{{ v.plate }}</bdi>
          <span>{{ v.vehicle_type || t("common.none") }}</span>
        </button>
        <StatusLabel :tone="vehicleStatusTone(v.vehicle_status)" :label="fmt.sb(v).label" />
      </header>

      <dl class="scan-context">
        <div>
          <dt>{{ t("table.colProject") }}</dt>
          <dd>{{ fmt.trim(v.project) || t("common.none") }}</dd>
        </div>
        <div>
          <dt>{{ t("table.colOffice") }}</dt>
          <dd>{{ v.rental_office || t("common.none") }}</dd>
        </div>
        <div>
          <dt>{{ t("table.colCurrentDriver") }}</dt>
          <dd>{{ driverName(v) }}</dd>
        </div>
      </dl>

      <div v-if="exceptions(v).length" class="scan-exceptions">
        <span v-for="item in exceptions(v)" :key="item.key" :data-tone="item.tone">
          <Icon :name="item.icon" :size="14" /> {{ item.label }}
        </span>
      </div>

      <footer class="scan-actions">
        <template v-if="v.vehicle_status === 'assigned'">
          <Button variant="outline" theme="red" size="lg" :disabled="isBusy(v.plate)" :label="t('card.stop')" @click="actions.quickStop(v.plate)" />
          <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.reassign')" @click="openVehicle(v.plate, 'driver')" />
          <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.quickStop(v.plate, true)" />
        </template>
        <template v-else-if="v.vehicle_status === 'available'">
          <Button variant="solid" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.assign')" @click="actions.quickReassign(v.plate)" />
          <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.sendWorkshop(v.plate)" />
          <Button variant="ghost" theme="red" size="lg" :disabled="isBusy(v.plate)" :label="t('card.markStolen')" @click="actions.markStolen(v.plate)" />
        </template>
        <template v-else-if="v.vehicle_status === 'workshop'">
          <Button variant="solid" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.exit')" @click="actions.exitWorkshop(v.plate)" />
        </template>
        <template v-else-if="v.vehicle_status === 'stolen'">
          <Button variant="solid" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.recover')" @click="actions.recoverVehicle(v.plate)" />
        </template>
        <template v-else>
          <Button variant="solid" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.available')" @click="actions.setAvailable(v.plate)" />
          <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.sendWorkshop(v.plate)" />
        </template>
        <Button class="scan-details" variant="ghost" size="lg" :label="t('table.details')" @click="openVehicle(v.plate)" />
      </footer>
    </article>
  </div>
</template>

<script setup>
import { Button, Checkbox } from "frappe-ui";

import StatusLabel from "@shared/components/StatusLabel.vue";

import Icon from "../Icon.vue";
import EmptyBoard from "./EmptyBoard.vue";
import { hasOpenIncident, vehicleStatusTone } from "../fleetHelpers.js";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, filters, selection, actions, density } = useBoardContext();
const { filtered } = filters;
const { selectMode, isSelected, toggleSelect, selectionLimitReached } = selection;
const { isBusy } = actions;
const { openVehicle } = state;

const driverName = (vehicle) => {
  const driver = vehicle.current_driver;
  return driver ? driver.name_ar || driver.name_en || t("common.none") : t("common.none");
};

const exceptions = (vehicle) => {
  const items = [];
  if (hasOpenIncident(vehicle)) {
    items.push({ key: "incident", tone: "danger", icon: "crash", label: t("topbar.openIncidents") });
  }
  if (fmt.expiryFlag(vehicle).show) {
    items.push({ key: "expiry", tone: "warning", icon: "shield-alert", label: fmt.expiryFlag(vehicle).label });
  }
  if (vehicle.workshop_overstay) {
    items.push({ key: "workshop", tone: "warning", icon: "wrench", label: t("topbar.workshopOverstay") });
  }
  return items;
};
</script>
