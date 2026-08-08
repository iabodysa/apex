<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="cards-wrap">
    <EmptyBoard v-if="!filtered.length" icon="user" />

    <div v-else class="fp-lens">
      <section v-for="g in driverGroups" :key="g.key" class="fp-lens-group">
        <header class="fp-lens-head">
          <span class="fp-lens-av">
            <bdi v-if="g.driver">{{ fmt.initials(g.driver) }}</bdi>
            <Icon v-else name="car" :size="15" />
          </span>
          <h2 class="fp-lens-name">
            <template v-if="g.driver">
              {{ g.driver.name_ar || g.driver.name_en || t("common.none") }}
            </template>
            <template v-else>{{ t("lens.unassigned") }}</template>
          </h2>
          <span class="fp-lens-count">{{ t("lens.vehiclesCount", { n: g.vehicles.length }) }}</span>
        </header>

        <button
          v-for="v in g.vehicles"
          :key="v.plate"
          type="button"
          class="fp-lens-row"
          :class="'vs-' + v.vehicle_status"
          @click="openVehicle(v.plate)"
        >
          <Icon :name="fmt.icon(v)" :size="16" />
          <span class="fp-lens-plate mono"><bdi>{{ v.plate }}</bdi></span>
          <Badge :theme="fmt.sb(v).theme" size="sm" :label="fmt.sl(v.vehicle_status)" />
          <span class="fp-lens-meta">
            {{ v.vehicle_type || t("common.none") }} · {{ fmt.trim(v.project) || t("common.none") }}
          </span>
          <Icon name="chevron" :size="14" class="fp-lens-chev" />
        </button>
      </section>
    </div>
  </div>
</template>

<script setup>
import { Badge } from "frappe-ui";

import Icon from "../Icon.vue";
import EmptyBoard from "./EmptyBoard.vue";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, filters } = useBoardContext();
const { filtered, driverGroups } = filters;
const { openVehicle } = state;
</script>
