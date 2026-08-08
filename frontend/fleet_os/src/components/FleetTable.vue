<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "filtered", "isScopeEmpty", "selectMode", "allVisibleSelected", "toggleSelectAll",
  "isSelected", "toggleSelect", "onSortCol", "openPanel",
  "icon", "sb", "sl", "trim", "calcTotalDaysNum", "t",
]);
</script>

<template>
  <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-if="selectMode" style="width:34px"><input type="checkbox" class="fp-sel-box" :checked="allVisibleSelected" @click="toggleSelectAll" /></th>
              <th @click="onSortCol('sheet')">{{ t("table.colType") }}</th>
              <th @click="onSortCol('plate')">{{ t("table.colPlate") }}</th>
              <th @click="onSortCol('vehicle_type')">{{ t("table.colVehicle") }}</th>
              <th @click="onSortCol('rental_office')">{{ t("table.colOffice") }}</th>
              <th @click="onSortCol('status')">{{ t("table.colStatus") }}</th>
              <th>{{ t("table.colCurrentDriver") }}</th>
              <th @click="onSortCol('project')">{{ t("table.colProject") }}</th>
              <th @click="onSortCol('area')">{{ t("table.colArea") }}</th>
              <th @click="onSortCol('drivers_desc')">{{ t("table.colDriverCount") }}</th>
              <th @click="onSortCol('duration_desc')">{{ t("table.colRunningDays") }}</th>
              <th>{{ t("table.colAction") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filtered.length"><td :colspan="selectMode ? 12 : 11"><div class="empty"><div class="empty-ic"><Icon :name="isScopeEmpty ? 'lock' : 'search'" :size="42" :stroke-width="1.5" /></div>{{ isScopeEmpty ? t("main.noScope") : t("main.noResults") }}</div></td></tr>
            <tr v-for="v in filtered" :key="v.plate" :class="{ 'fp-sel': selectMode && isSelected(v.plate) }" @click="selectMode ? toggleSelect(v.plate) : openPanel(v.plate)">
              <td v-if="selectMode" @click.stop><input type="checkbox" class="fp-sel-box" :checked="isSelected(v.plate)" @click.stop="toggleSelect(v.plate)" /></td>
              <td><Icon :name="icon(v)" :size="18" /></td>
              <td><span class="mono" style="font-weight:700;color:var(--t1)"><bdi>{{ v.plate }}</bdi></span></td>
              <td>{{ v.vehicle_type }}</td>
              <td>{{ v.rental_office }}</td>
              <td><span class="sbadge" :class="sb(v).cls" style="display:inline-flex;gap:4px"><Icon :name="sb(v).ic" :size="12" />{{ sl(v.vehicle_status) }}</span></td>
              <td><template v-if="v.current_driver">{{ v.current_driver.name_ar || v.current_driver.name_en }} <Icon name="lock" :size="13" /></template><span v-else style="color:var(--t3)">—</span></td>
              <td>{{ trim(v.project) || t("common.none") }}</td>
              <td>{{ v.area }}</td>
              <td style="color:var(--critical-l)">{{ v.history.length }}</td>
              <td style="color:var(--amber-l);font-family:'JetBrains Mono',monospace">{{ calcTotalDaysNum(v) ? t("duration.dayUnit", { n: calcTotalDaysNum(v) }) : t("common.none") }}</td>
              <td @click.stop>
                <button class="btn" style="padding:3px 10px;font-size:11px" @click="openPanel(v.plate)">{{ t("table.details") }} <Icon name="chevron" :size="13" /></button>
              </td>
            </tr>
          </tbody>
        </table>
  </div>
</template>
