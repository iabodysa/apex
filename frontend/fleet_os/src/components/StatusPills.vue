<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="fp-pills-bar" role="group" :aria-label="t('topbar.filterByStatus')">
    <template v-if="countsLoading">
      <span v-for="n in 6" :key="n" class="sp fp-kpi-skel" aria-hidden="true"></span>
    </template>
    <template v-else>
      <!-- Each counter is a filter, not a label: pressing it narrows the board, and pressing
           the one already applied clears it. -->
      <button
        v-for="pill in pills"
        :key="pill.key"
        type="button"
        class="sp"
        :class="['sp-' + (pill.key || 'all'), { active: status === pill.key }]"
        :aria-pressed="status === pill.key"
        @click="pill.key ? toggleFilter('status', pill.key) : setFilter('status', '')"
      >
        <b>{{ pill.count }}</b> {{ pill.label }}
      </button>

      <button
        v-if="triage.incidents"
        type="button"
        class="sp sp-triage-incident"
        :class="{ active: triageKey === 'incidents' }"
        :aria-pressed="triageKey === 'incidents'"
        @click="toggleFilter('triage', 'incidents')"
      >
        <Icon name="crash" :size="12" /> <b>{{ triage.incidents }}</b> {{ t("topbar.openIncidents") }}
      </button>
      <button
        v-if="triage.expiring"
        type="button"
        class="sp sp-triage-expiry"
        :class="{ active: triageKey === 'expiring' }"
        :aria-pressed="triageKey === 'expiring'"
        @click="toggleFilter('triage', 'expiring')"
      >
        <Icon name="shield-alert" :size="12" /> <b>{{ triage.expiring }}</b> {{ t("topbar.expiringSoon") }}
      </button>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, board } = useBoardContext();
const { counts, countsLoading, triage } = board;
const { setFilter, toggleFilter } = state;

const status = computed(() => state.f.status.value);
const triageKey = computed(() => state.f.triage.value);

const pills = computed(() => [
  { key: "", count: counts.value.total, label: t("topbar.allVehicles") },
  { key: "assigned", count: counts.value.assigned, label: t("statusShort.assigned") },
  { key: "available", count: counts.value.available, label: t("statusShort.available") },
  { key: "workshop", count: counts.value.workshop, label: t("statusShort.workshop") },
  { key: "stopped", count: counts.value.stopped, label: t("statusShort.stopped") },
  { key: "stolen", count: counts.value.stolen, label: t("statusShort.stolen") },
]);
</script>
