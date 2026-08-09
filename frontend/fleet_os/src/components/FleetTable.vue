<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <EmptyBoard v-if="!filtered.length" icon="search" />

  <template v-else>
    <DataLedger class="ledger-desktop" :label="t('main.workingSet')">
      <template #head>
        <tr>
          <th v-if="selectMode" class="select-column">
            <Checkbox
              :model-value="allVisibleSelected"
              :label="t('bulk.selectAll')"
              @update:model-value="toggleSelectAll()"
            />
          </th>
          <th
            v-for="col in columns"
            :key="col.label"
            :aria-sort="col.key ? ariaSort(col.key) : undefined"
          >
            <button v-if="col.key" type="button" class="column-sort" @click="setSort(col.key)">
              {{ col.label }}
              <Icon
                v-if="sort === col.key"
                name="chevron"
                :size="12"
                :class="sortDir === 1 ? 'sort-asc' : 'sort-desc'"
              />
            </button>
            <span v-else>{{ col.label }}</span>
          </th>
          <th>{{ t("table.colAction") }}</th>
        </tr>
      </template>

      <tr
        v-for="v in filtered"
        :key="v.plate"
        :class="{ 'is-selected': selectMode && isSelected(v.plate), 'has-exception': hasException(v) }"
      >
        <td v-if="selectMode">
          <Checkbox
            :model-value="isSelected(v.plate)"
            :disabled="selectionLimitReached && !isSelected(v.plate)"
            :label="t('bulk.selectOne', { plate: v.plate })"
            @update:model-value="toggleSelect(v.plate)"
          />
        </td>
        <td>
          <span class="vehicle-id">
            <Icon :name="fmt.icon(v)" :size="18" />
            <bdi class="mono plate">{{ v.plate }}</bdi>
          </span>
        </td>
        <td>
          <StatusLabel :tone="vehicleStatusTone(v.vehicle_status)" :label="fmt.sl(v.vehicle_status)" />
        </td>
        <td>
          <span v-if="v.current_driver" class="driver-name">
            {{ v.current_driver.name_ar || v.current_driver.name_en || t("common.none") }}
          </span>
          <span v-else class="muted">{{ t("common.none") }}</span>
        </td>
        <td>{{ fmt.trim(v.project) || t("common.none") }}</td>
        <td>{{ v.rental_office || t("common.none") }}</td>
        <td>{{ v.area || t("common.none") }}</td>
        <td>
          <span v-if="hasException(v)" class="exception-stack">
            <span v-if="hasOpenIncident(v)">{{ t("topbar.openIncidents") }}</span>
            <span v-if="fmt.expiryFlag(v).show">{{ fmt.expiryFlag(v).label }}</span>
            <span v-if="v.workshop_overstay">{{ t("topbar.workshopOverstay") }}</span>
          </span>
          <span v-else class="muted">{{ t("table.clear") }}</span>
        </td>
        <td>
          <Button variant="ghost" size="lg" :label="t('table.details')" @click="openVehicle(v.plate)">
            <template #suffix><Icon name="chevron" :size="13" /></template>
          </Button>
        </td>
      </tr>
    </DataLedger>

    <div class="ledger-mobile" :aria-label="t('main.workingSet')">
      <article
        v-for="v in prioritized"
        :key="v.plate"
        class="mobile-signal-row"
        :class="{ 'is-selected': selectMode && isSelected(v.plate) }"
      >
        <header>
          <Checkbox
            v-if="selectMode"
            :model-value="isSelected(v.plate)"
            :disabled="selectionLimitReached && !isSelected(v.plate)"
            :label="t('bulk.selectOne', { plate: v.plate })"
            @update:model-value="toggleSelect(v.plate)"
          />
          <span class="vehicle-id">
            <Icon :name="fmt.icon(v)" :size="18" />
            <bdi class="mono plate">{{ v.plate }}</bdi>
          </span>
          <StatusLabel :tone="vehicleStatusTone(v.vehicle_status)" :label="fmt.sl(v.vehicle_status)" />
        </header>

        <p class="mobile-vehicle-line">
          {{ v.vehicle_type || t("common.none") }}
          <span aria-hidden="true">·</span>
          {{ fmt.trim(v.project) || t("common.none") }}
        </p>
        <p v-if="v.current_driver" class="mobile-driver">
          <Icon name="user" :size="14" />
          {{ v.current_driver.name_ar || v.current_driver.name_en || t("common.none") }}
        </p>

        <div v-if="hasException(v)" class="mobile-exceptions">
          <span v-if="hasOpenIncident(v)"><Icon name="crash" :size="14" /> {{ t("topbar.openIncidents") }}</span>
          <span v-if="fmt.expiryFlag(v).show"><Icon name="shield-alert" :size="14" /> {{ fmt.expiryFlag(v).label }}</span>
          <span v-if="v.workshop_overstay"><Icon name="wrench" :size="14" /> {{ t("topbar.workshopOverstay") }}</span>
        </div>

        <Button variant="outline" size="xl" :label="t('table.details')" @click="openVehicle(v.plate)">
          <template #suffix><Icon name="chevron" :size="14" /></template>
        </Button>
      </article>
    </div>
  </template>
</template>

<script setup>
import { computed } from "vue";
import { Button, Checkbox } from "frappe-ui";

import DataLedger from "@shared/components/DataLedger.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";

import Icon from "../Icon.vue";
import EmptyBoard from "./EmptyBoard.vue";
import { hasOpenIncident, vehicleStatusTone } from "../fleetHelpers.js";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, filters, selection } = useBoardContext();
const { filtered } = filters;
const {
  selectMode,
  isSelected,
  toggleSelect,
  allVisibleSelected,
  toggleSelectAll,
  selectionLimitReached,
} = selection;
const { sort, sortDir, setSort, openVehicle } = state;

const columns = computed(() => [
  { label: t("table.colVehicle"), key: "plate" },
  { label: t("table.colStatus"), key: "status" },
  { label: t("table.colCurrentDriver"), key: null },
  { label: t("table.colProject"), key: "project" },
  { label: t("table.colOffice"), key: "rental_office" },
  { label: t("table.colArea"), key: "area" },
  { label: t("table.colAttention"), key: null },
]);

const hasException = (vehicle) =>
  hasOpenIncident(vehicle) || fmt.expiryFlag(vehicle).show || vehicle.workshop_overstay === true;

const priority = (vehicle) => {
  if (vehicle.vehicle_status === "stolen") return 0;
  if (hasOpenIncident(vehicle)) return 1;
  if (fmt.expiryFlag(vehicle).expired) return 2;
  if (vehicle.workshop_overstay) return 3;
  if (fmt.expiryFlag(vehicle).show) return 4;
  return 5;
};

const prioritized = computed(() =>
  filtered.value.slice().sort((a, b) => priority(a) - priority(b)),
);

const ariaSort = (key) => {
  if (sort.value !== key) return "none";
  return sortDir.value === 1 ? "ascending" : "descending";
};
</script>
