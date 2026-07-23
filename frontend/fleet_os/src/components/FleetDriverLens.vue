<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Driver-centric lens: the same filtered vehicles grouped by current driver. -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "filtered", "isScopeEmpty", "anyFilterActive", "resetFilters", "driverGroups",
  "initials", "icon", "sb", "sl", "trim", "openPanel", "t",
]);
</script>

<template>
  <div class="cards-wrap">
        <div v-if="!filtered.length" class="empty">
          <div class="empty-ic"><Icon :name="isScopeEmpty ? 'lock' : 'user'" :size="42" :stroke-width="1.5" /></div>
          <div>{{ isScopeEmpty ? t("main.noScope") : anyFilterActive ? t("main.noResultsFilters") : t("main.noVehicles") }}</div>
          <button v-if="!isScopeEmpty && anyFilterActive" class="btn btn-blue" @click="resetFilters">{{ t("main.clearFilters") }}</button>
        </div>
        <div v-else class="fp-lens">
          <div v-for="g in driverGroups" :key="g.key" class="fp-lens-group">
            <div class="fp-lens-head">
              <span class="fp-lens-av">
                <template v-if="g.driver"><bdi>{{ initials(g.driver) }}</bdi></template>
                <Icon v-else name="car" :size="15" />
              </span>
              <span class="fp-lens-name">
                <template v-if="g.driver">{{ g.driver.name_ar || g.driver.name_en || t("common.none") }}</template>
                <template v-else>{{ t("lens.unassigned") }}</template>
              </span>
              <span class="fp-lens-count">{{ t("lens.vehiclesCount", { n: g.vehicles.length }) }}</span>
            </div>
            <button
              v-for="v in g.vehicles"
              :key="v.plate"
              class="fp-lens-row"
              :class="'vs-' + v.vehicle_status"
              @click="openPanel(v.plate)"
            >
              <Icon :name="icon(v)" :size="16" class="shrink-0" />
              <span class="fp-lens-plate mono"><bdi>{{ v.plate }}</bdi></span>
              <span class="sbadge" :class="sb(v).cls"><Icon :name="sb(v).ic" :size="12" />{{ sl(v.vehicle_status) }}</span>
              <span class="fp-lens-meta">{{ v.vehicle_type || "—" }} · {{ trim(v.project) || t("common.none") }}</span>
              <Icon name="chevron" :size="14" class="fp-lens-chev shrink-0" />
            </button>
          </div>
        </div>
  </div>
</template>
