<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <!-- The library's Dialog rather than a hand-rolled overlay: it portals, traps the focus,
       closes on Escape and gives the focus back — none of which the old drawer did. -->
  <Dialog v-model="open" :options="{ title: t('alerts.title'), size: 'lg' }">
    <template #body-content>
      <div class="ad-body">
        <div v-if="alertsState === 'loading'" class="ad-skel" aria-hidden="true">
          <div v-for="n in 3" :key="n" class="fp-skel-line"></div>
        </div>

        <LoadError
          v-else-if="alertsState === 'error'"
          :title="t('alerts.loadError')"
          :detail="alertsError"
          :hint="t('main.loadFailedHint')"
          :retry-label="t('common.retry')"
          @retry="loadAlerts()"
        />

        <EmptyState v-else-if="!alerts.length" :title="t('alerts.empty')" :hint="t('alerts.emptyHint')">
          <template #icon><Icon name="bell" :size="20" :stroke-width="1.6" /></template>
        </EmptyState>

        <template v-else>
        <button v-for="a in alerts" :key="a.name" type="button" class="ad-row" @click="openAlertTarget(a)">
          <span class="ad-row-top">
            <Badge :theme="sevTheme(a.severity)" size="sm" :label="sevLabel(a.severity)" />
            <span class="ad-when"><bdi>{{ a.raised_on }}</bdi></span>
          </span>
          <span class="ad-msg">{{ a.message }}</span>
          <span class="ad-meta">
            <bdi v-if="a.vehicle_plate">{{ a.vehicle_plate }}</bdi>
            <span v-if="a.driver_name">· {{ a.driver_name }}</span>
            <span class="ad-link">
              {{ alertVehicleOnBoard(a) ? t("alerts.viewVehicle") : t("alerts.openInDesk") }}
            </span>
          </span>
        </button>
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, watch } from "vue";
import { Badge, Dialog } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, alerts: api } = useBoardContext();
const { alerts, alertsState, alertsError, loadAlerts, sevTheme, sevLabel, alertVehicleOnBoard, openAlertTarget } = api;

/* The drawer is a place in the address, so Back closes it and a link can open it. */
const open = computed({
  get: () => state.alertsOpen.value,
  set: (value) => state.setAlerts(value),
});

/* Opening the drawer is the moment the supervisor asked to see the alerts, so they are read
   again then — the background poll may be many seconds old. */
watch(open, (isOpen) => {
  if (isOpen) loadAlerts();
});
</script>
