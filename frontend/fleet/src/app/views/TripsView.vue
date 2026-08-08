<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-narrow">
    <section class="emp-card">
      <header class="emp-card-head">
        <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
        <div class="emp-card-titles">
          <h2>{{ t("emp.trips.title") }}</h2>
          <p class="emp-hint">{{ t("emp.trips.windowHint") }}</p>
        </div>
      </header>

      <div v-if="trips.state.status === 'loading'" class="emp-skel" aria-hidden="true" />

      <LoadError
        v-else-if="trips.state.status === 'error'"
        :title="t('emp.loadError')"
        :detail="trips.state.error"
        :hint="t('emp.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="trips.reload()"
      />

      <EmptyState
        v-else-if="!trips.state.data.length"
        :title="t('emp.trips.empty')"
        :hint="t('emp.trips.emptyHint')"
      >
        <template #icon><Icon name="clipboard-list" :size="20" /></template>
      </EmptyState>

      <TripList v-else :rows="trips.state.data" />
    </section>
  </div>
</template>

<script setup>
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import TripList from "../components/TripList.vue";
import { useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const { trips } = useEmployee();
</script>
