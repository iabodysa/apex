<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Operations-alert drawer: the scoped open-alert queue with deep links. -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "alertsOpen", "alertsState", "alerts", "alertTotal", "closeAlerts", "loadAlerts",
  "sevClass", "sevLabel", "alertVehicleOnBoard", "openAlertTarget", "t",
]);
</script>

<template>
  <!-- ALERT DRAWER -->
  <transition name="fp-overlay">
    <!-- Backdrop only duplicates the labelled close button, so it is hidden from AT. -->
    <div v-if="alertsOpen" class="panel-overlay open" aria-hidden="true" @click.self="closeAlerts"></div>
  </transition>
  <transition name="fp-panel">
    <div v-if="alertsOpen" class="alert-drawer">
      <div class="panel-head">
        <div class="ph-left">
          <div class="ph-plate"><Icon name="bell" :size="18" /> {{ t("alerts.title") }}</div>
          <div class="ph-sub">{{ alertTotal }}</div>
        </div>
        <!-- Icon-only: IconBase marks its svg aria-hidden, so the name must come from aria-label. -->
        <button class="panel-close" :aria-label="t('alerts.close')" @click="closeAlerts"><Icon name="x" :size="18" /></button>
      </div>
      <div class="panel-body">
        <div v-if="alertsState === 'loading'" class="ad-empty">{{ t("alerts.title") }}…</div>
        <div v-else-if="alertsState === 'error'" class="alert alert-red" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          {{ t("alerts.loadError") }}
          <button class="btn btn-red" style="margin-inline-start:auto" @click="loadAlerts">{{ t("common.retry") }}</button>
        </div>
        <div v-else-if="!alerts.length" class="ad-empty">{{ t("alerts.empty") }}</div>
        <button v-for="a in alerts" v-else :key="a.name" class="ad-row" :class="sevClass(a.severity)" @click="openAlertTarget(a)">
          <div class="ad-row-top">
            <span class="ad-sev">{{ sevLabel(a.severity) }}</span>
            <span class="ad-when">{{ a.raised_on }}</span>
          </div>
          <div class="ad-msg">{{ a.message }}</div>
          <div class="ad-meta">
            <span v-if="a.vehicle_plate"><bdi>{{ a.vehicle_plate }}</bdi></span>
            <span v-if="a.driver_name">· {{ a.driver_name }}</span>
            <span class="ad-link">{{ alertVehicleOnBoard(a) ? t("alerts.viewVehicle") : t("alerts.openInDesk") }}</span>
          </div>
        </button>
      </div>
    </div>
  </transition>
</template>
