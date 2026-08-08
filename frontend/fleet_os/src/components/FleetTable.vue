<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th v-if="selectMode" class="th-select">
            <Checkbox
              :model-value="allVisibleSelected"
              :label="t('bulk.selectAll')"
              @update:model-value="toggleSelectAll()"
            />
          </th>
          <!-- A sortable column is a button, so it is reachable by keyboard, and the header
               carries aria-sort so the direction is announced rather than merely implied. -->
          <th
            v-for="col in columns"
            :key="col.label"
            :aria-sort="col.key ? ariaSort(col.key) : undefined"
          >
            <button v-if="col.key" type="button" class="th-sort" @click="setSort(col.key)">
              {{ col.label }}
              <Icon v-if="sort === col.key" name="chevron" :size="12" :class="sortDir === 1 ? 'th-asc' : 'th-desc'" />
            </button>
            <span v-else>{{ col.label }}</span>
          </th>
          <th>{{ t("table.colAction") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!filtered.length">
          <td :colspan="selectMode ? columns.length + 2 : columns.length + 1">
            <EmptyBoard icon="search" />
          </td>
        </tr>
        <tr v-for="v in filtered" :key="v.plate" :class="{ 'fp-sel': selectMode && isSelected(v.plate) }">
          <td v-if="selectMode">
            <Checkbox
              :model-value="isSelected(v.plate)"
              :label="t('bulk.selectOne', { plate: v.plate })"
              @update:model-value="toggleSelect(v.plate)"
            />
          </td>
          <td><Icon :name="fmt.icon(v)" :size="18" /></td>
          <td><span class="mono td-plate"><bdi>{{ v.plate }}</bdi></span></td>
          <td>{{ v.vehicle_type || t("common.none") }}</td>
          <td>{{ v.rental_office || t("common.none") }}</td>
          <td><Badge :theme="fmt.sb(v).theme" size="sm" :label="fmt.sl(v.vehicle_status)" /></td>
          <td>
            <template v-if="v.current_driver">
              {{ v.current_driver.name_ar || v.current_driver.name_en }}
            </template>
            <span v-else class="td-muted">{{ t("common.none") }}</span>
          </td>
          <td>{{ fmt.trim(v.project) || t("common.none") }}</td>
          <td>{{ v.area || t("common.none") }}</td>
          <td class="mono">{{ v.history.length }}</td>
          <td class="mono">
            {{ fmt.calcTotalDaysNum(v) ? t("duration.dayUnit", { n: fmt.calcTotalDaysNum(v) }) : t("common.none") }}
          </td>
          <td>
            <Button variant="outline" size="lg" :label="t('table.details')" @click="openVehicle(v.plate)">
              <template #suffix><Icon name="chevron" :size="13" /></template>
            </Button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Button, Checkbox } from "frappe-ui";

import Icon from "../Icon.vue";
import EmptyBoard from "./EmptyBoard.vue";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, filters, selection } = useBoardContext();
const { filtered } = filters;
const { selectMode, isSelected, toggleSelect, allVisibleSelected, toggleSelectAll } = selection;
const { sort, sortDir, setSort, openVehicle } = state;

const columns = computed(() => [
  { label: t("table.colType"), key: "sheet" },
  { label: t("table.colPlate"), key: "plate" },
  { label: t("table.colVehicle"), key: "vehicle_type" },
  { label: t("table.colOffice"), key: "rental_office" },
  { label: t("table.colStatus"), key: "status" },
  { label: t("table.colCurrentDriver"), key: null },
  { label: t("table.colProject"), key: "project" },
  { label: t("table.colArea"), key: "area" },
  { label: t("table.colDriverCount"), key: "drivers_desc" },
  { label: t("table.colRunningDays"), key: "duration_desc" },
]);

const ariaSort = (key) => {
  if (sort.value !== key) return "none";
  return sortDir.value === 1 ? "ascending" : "descending";
};
</script>
