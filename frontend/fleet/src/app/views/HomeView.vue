<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-grid">
    <div class="emp-col">
      <section class="emp-card">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="car" :size="17" /></span>
          <div class="emp-card-titles">
            <h2>{{ t("emp.vehicle.title") }}</h2>
            <p class="emp-hint">{{ t("emp.vehicle.hint") }}</p>
          </div>
        </header>

        <div v-if="vehicle.state.status === 'loading'" class="emp-skel" aria-hidden="true" />

        <LoadError
          v-else-if="vehicle.state.status === 'error'"
          :title="t('emp.loadError')"
          :detail="vehicle.state.error"
          :hint="t('emp.loadErrorHint')"
          :retry-label="t('common.retry')"
          @retry="vehicle.reload()"
        />

        <EmptyState
          v-else-if="!vehicle.state.data"
          :title="t('emp.vehicle.empty')"
          :hint="t('emp.vehicle.emptyHint')"
        >
          <template #icon><Icon name="car" :size="20" /></template>
        </EmptyState>

        <template v-else>
          <div class="emp-vehicle-hero">
            <bdi class="emp-plate">{{ vehicle.state.data.plate }}</bdi>
            <div class="emp-vinfo">
              <b>{{ vehicle.state.data.model || t("common.none") }}</b>
              <span>{{ vehicle.state.data.office || t("common.none") }}</span>
            </div>
            <Badge
              class="emp-vehicle-status"
              :theme="vehicleMeta(vehicle.state.data.status).theme"
              size="md"
              :label="t(vehicleMeta(vehicle.state.data.status).key)"
            />
          </div>

          <div class="emp-kv-row">
            <div class="emp-kv">
              <small><Icon name="gauge" :size="13" /> {{ t("emp.vehicle.odometer") }}</small>
              <b class="tnum">
                <bdi>{{ formatInt(vehicle.state.data.odometerKm, lang) }}</bdi>
                {{ t("emp.vehicle.kmUnit") }}
              </b>
            </div>
            <div class="emp-kv">
              <small><Icon name="calendar" :size="13" /> {{ t("emp.vehicle.registration") }}</small>
              <b>
                <template v-if="vehicle.state.data.registrationExpiry">
                  {{ t("emp.vehicle.validUntil", { date: vehicle.state.data.registrationExpiry }) }}
                </template>
                <template v-else>{{ t("common.none") }}</template>
              </b>
            </div>
          </div>
        </template>
      </section>

      <section class="emp-card">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
          <div class="emp-card-titles">
            <h2>{{ t("emp.trips.title") }}</h2>
            <p class="emp-hint">{{ t("emp.trips.previewHint") }}</p>
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

        <template v-else>
          <TripList :rows="tripPreview" />
          <Button
            class="emp-block-btn"
            variant="outline"
            size="xl"
            :label="t('emp.trips.viewAll')"
            @click="router.push('/trips')"
          />
        </template>
      </section>
    </div>

    <section class="emp-card">
      <header class="emp-card-head">
        <span class="emp-ic"><Icon name="fuel" :size="17" /></span>
        <div class="emp-card-titles">
          <h2>{{ t("emp.fuel.title") }}</h2>
          <p class="emp-hint">{{ t("emp.fuel.cardHint") }}</p>
        </div>
      </header>

      <!-- This card used to be a heading and a link to a screen the nav bar already offers. It
           now answers the question it is named after: what happened to what I asked for. -->
      <div v-if="fuelRequests.state.status === 'loading'" class="emp-skel" aria-hidden="true" />

      <LoadError
        v-else-if="fuelRequests.state.status === 'error'"
        :title="t('emp.loadError')"
        :detail="fuelRequests.state.error"
        :hint="t('emp.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="fuelRequests.reload()"
      />

      <template v-else>
        <div v-if="latestFuelRequest" class="emp-fuel-state">
          <div class="emp-kv">
            <small>{{ t("emp.fuel.lastRequest") }}</small>
            <b>
              <bdi>{{ latestFuelRequest.litres }}</bdi> {{ t("emp.fuel.litresUnit") }}
              <template v-if="latestFuelRequest.date"> · <bdi>{{ latestFuelRequest.date }}</bdi></template>
            </b>
          </div>
          <Badge
            :theme="fuelMeta(latestFuelRequest.statusKey).theme"
            size="md"
            :label="t(fuelMeta(latestFuelRequest.statusKey).key)"
          />
        </div>
        <p v-else class="emp-hint">{{ t("emp.fuel.historyEmpty") }}</p>

        <p v-if="pendingFuelCount" class="emp-hint emp-pending-note">
          {{ t("emp.fuel.pendingCount", { n: pendingFuelCount }) }}
        </p>

        <Button
          class="emp-block-btn"
          variant="solid"
          theme="green"
          size="xl"
          :label="t('emp.fuel.newRequest')"
          @click="router.push('/fuel')"
        >
          <template #prefix><Icon name="fuel" :size="17" /></template>
        </Button>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Badge, Button } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import TripList from "../components/TripList.vue";
import { formatInt } from "../fmt.js";
import { fuelMeta, vehicleMeta } from "../statusMeta.js";
import { useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t, lang } = useI18n();
const router = useRouter();
const { vehicle, trips, fuelRequests, latestFuelRequest, pendingFuelCount } = useEmployee();

const tripPreview = computed(() => trips.state.data.slice(0, 2));
</script>
