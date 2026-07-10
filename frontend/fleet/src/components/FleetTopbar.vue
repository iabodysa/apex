<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Top bar: brand, global search, KPI/status pills, triage pills, alert bell. -->
<script setup>
import Icon from "./Icon.vue";
import LangToggle from "./LangToggle.vue";
defineProps([
  "f", "counts", "countsLoading", "triage", "triageFilter",
  "alertTotal", "alertsOpen", "setSP", "setTriage", "toggleAlerts", "t",
]);
</script>

<template>
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge"><Icon name="car" :size="20" /></div>
      <div>
        <div class="brand-name">{{ t("brand.name") }}</div>
      </div>
    </div>
    <div class="search-bar">
      <span class="si"><Icon name="search" :size="15" /></span>
      <input v-model="f.search" :placeholder="t('topbar.searchPlaceholder')" />
    </div>
    <!-- KPI pills shimmer until the first load resolves so they don't flash 0 -->
    <div v-if="countsLoading" class="status-pills">
      <span v-for="n in 6" :key="n" class="sp fp-kpi-skel"></span>
    </div>
    <div v-else class="status-pills">
      <span class="sp sp-all" :class="{ active: f.status === '' }" @click="setSP('')">{{ counts.total }} {{ t("topbar.allVehicles") }}</span>
      <span class="sp sp-assigned" :class="{ active: f.status === 'assigned' }" @click="setSP('assigned')">{{ counts.assigned }} {{ t("statusShort.assigned") }}</span>
      <span class="sp sp-available" :class="{ active: f.status === 'available' }" @click="setSP('available')">{{ counts.available }} {{ t("statusShort.available") }}</span>
      <span class="sp sp-workshop" :class="{ active: f.status === 'workshop' }" @click="setSP('workshop')">{{ counts.workshop }} {{ t("statusShort.workshop") }}</span>
      <span class="sp sp-stopped" :class="{ active: f.status === 'stopped' }" @click="setSP('stopped')">{{ counts.stopped }} {{ t("statusShort.stopped") }}</span>
      <span class="sp sp-stolen" :class="{ active: f.status === 'stolen' }" @click="setSP('stolen')">{{ counts.stolen }} {{ t("statusShort.stolen") }}</span>
      <!-- Derived triage pills (open incidents / expiring soon) → client filters -->
      <span v-if="triage.incidents" class="sp sp-triage-incident" :class="{ active: triageFilter === 'incidents' }" @click="setTriage('incidents')"><Icon name="crash" :size="12" /> {{ triage.incidents }} {{ t("topbar.openIncidents") }}</span>
      <span v-if="triage.expiring" class="sp sp-triage-expiry" :class="{ active: triageFilter === 'expiring' }" @click="setTriage('expiring')"><Icon name="shield-alert" :size="12" /> {{ triage.expiring }} {{ t("topbar.expiringSoon") }}</span>
    </div>
    <button class="alert-bell" :class="{ active: alertsOpen }" :title="t('alerts.bellTitle')" :aria-label="t('alerts.bellTitle')" @click="toggleAlerts">
      <Icon name="bell" :size="18" />
      <span v-if="alertTotal > 0" class="alert-bell-badge">{{ alertTotal > 99 ? "99+" : alertTotal }}</span>
    </button>
    <LangToggle />
  </div>
</template>
