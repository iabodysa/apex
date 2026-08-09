<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="attention-ribbon" :aria-label="t('topbar.attentionTitle')">
    <header class="attention-heading">
      <p>{{ t("topbar.attentionEyebrow") }}</p>
      <h2>{{ t("topbar.attentionTitle") }}</h2>
    </header>

    <div v-if="countsLoading" class="attention-stream" aria-hidden="true">
      <span v-for="n in 5" :key="n" class="signal signal-skeleton"></span>
    </div>

    <div v-else class="attention-stream" role="group" :aria-label="t('topbar.filterByStatus')">
      <button
        type="button"
        class="signal signal-alerts"
        @click="setAlerts(true)"
      >
        <Icon name="bell" :size="17" />
        <span>{{ t("topbar.openAlerts") }}</span>
        <bdi>{{ alertTotal }}</bdi>
      </button>

      <button
        v-for="item in exceptions"
        :key="item.key"
        type="button"
        class="signal"
        :class="['signal-' + item.tone, { active: triageKey === item.key }]"
        :aria-pressed="triageKey === item.key"
        @click="toggleFilter('triage', item.key)"
      >
        <Icon :name="item.icon" :size="17" />
        <span>{{ item.label }}</span>
        <bdi>{{ item.count }}</bdi>
      </button>

      <button
        v-for="pill in pills"
        :key="pill.key"
        type="button"
        class="signal signal-status"
        :class="[{ active: status === pill.key }, 'signal-' + pill.tone]"
        :aria-pressed="status === pill.key"
        @click="pill.key ? toggleFilter('status', pill.key) : setFilter('status', '')"
      >
        <span>{{ pill.label }}</span>
        <bdi>{{ pill.count }}</bdi>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, board, alerts } = useBoardContext();
const { counts, countsLoading, triage } = board;
const { setFilter, toggleFilter, setAlerts } = state;
const { alertTotal } = alerts;

const status = computed(() => state.f.status.value);
const triageKey = computed(() => state.f.triage.value);

const pills = computed(() => [
  { key: "", count: counts.value.total, label: t("topbar.allVehicles"), tone: "neutral" },
  { key: "assigned", count: counts.value.assigned, label: t("statusShort.assigned"), tone: "success" },
  { key: "available", count: counts.value.available, label: t("statusShort.available"), tone: "info" },
  { key: "workshop", count: counts.value.workshop, label: t("statusShort.workshop"), tone: "warning" },
  { key: "stopped", count: counts.value.stopped, label: t("statusShort.stopped"), tone: "neutral" },
  { key: "stolen", count: counts.value.stolen, label: t("statusShort.stolen"), tone: "danger" },
]);

const exceptions = computed(() => [
  {
    key: "incidents",
    count: triage.value.incidents,
    label: t("topbar.openIncidents"),
    icon: "crash",
    tone: "danger",
  },
  {
    key: "expiring",
    count: triage.value.expiring,
    label: t("topbar.expiringSoon"),
    icon: "shield-alert",
    tone: "warning",
  },
  {
    key: "workshop",
    count: triage.value.workshop,
    label: t("topbar.workshopOverstay"),
    icon: "wrench",
    tone: "warning",
  },
]);
</script>
