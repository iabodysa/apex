<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-narrow emp-history-scene">
    <section class="emp-sheet" aria-labelledby="emp-history-heading">
      <header class="emp-ledger-head">
        <div>
          <span class="emp-ledger-kicker">{{ t("emp.trips.windowLabel") }}</span>
          <h2 id="emp-history-heading">{{ t("emp.trips.historyTitle") }}</h2>
        </div>
        <strong class="emp-ledger-count tnum">
          <bdi>{{ formatInt(trips.state.data.length, lang) }}</bdi>
          <span>{{ t("emp.trips.countLabel") }}</span>
        </strong>
      </header>

      <AsyncBoundary
        :state="tripsState"
        :title="tripsState === 'empty' ? t('emp.trips.empty') : t('emp.loadError')"
        :message="tripsState === 'empty' ? t('emp.trips.emptyHint') : trips.state.error"
        :retry-label="t('common.retry')"
        @retry="trips.reload()"
      >
        <TripList :rows="trips.state.data" />
      </AsyncBoundary>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";

import TripList from "../components/TripList.vue";
import { formatInt } from "../fmt.js";
import { useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t, lang } = useI18n();
const { trips } = useEmployee();

const tripsState = computed(() => {
  if (trips.state.status === "loading" || trips.state.status === "idle") return "loading";
  if (trips.state.status === "error") return "error";
  return trips.state.data.length ? "ready" : "empty";
});
</script>
