<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-grid emp-today">
    <div class="emp-sheet emp-today-ledger">
      <section class="emp-section emp-vehicle-section" aria-labelledby="emp-vehicle-title">
        <header class="emp-section-head">
          <span class="emp-section-index" aria-hidden="true"><bdi>01</bdi></span>
          <div>
            <h2 id="emp-vehicle-title">{{ t("emp.vehicle.title") }}</h2>
            <p>{{ t("emp.vehicle.hint") }}</p>
          </div>
        </header>

        <AsyncBoundary
          :state="vehicleState"
          :title="vehicleState === 'empty' ? t('emp.vehicle.empty') : t('emp.loadError')"
          :message="vehicleState === 'empty' ? t('emp.vehicle.emptyHint') : vehicle.state.error"
          :retry-label="t('common.retry')"
          @retry="vehicle.reload()"
        >
          <div class="emp-vehicle-lockup">
            <div class="emp-plate-block">
              <span>{{ t("emp.vehicle.plateLabel") }}</span>
              <bdi class="emp-plate">{{ vehicle.state.data.plate || t("common.none") }}</bdi>
            </div>
            <div class="emp-vehicle-identity">
              <strong><bdi>{{ vehicle.state.data.model || t("common.none") }}</bdi></strong>
              <span><bdi>{{ vehicle.state.data.office || t("common.none") }}</bdi></span>
            </div>
            <Badge
              :theme="vehicleMeta(vehicle.state.data.status).theme"
              size="md"
              :label="t(vehicleMeta(vehicle.state.data.status).key)"
            />
          </div>

          <VehicleFacts :facts="vehicleFacts" :empty-value="t('common.none')" />
        </AsyncBoundary>
      </section>

      <section class="emp-section" aria-labelledby="emp-trip-title">
        <header class="emp-section-head">
          <span class="emp-section-index" aria-hidden="true"><bdi>02</bdi></span>
          <div>
            <h2 id="emp-trip-title">{{ t("emp.today.tripTitle") }}</h2>
            <p>{{ t("emp.trips.previewHint") }}</p>
          </div>
        </header>

        <AsyncBoundary
          :state="tripsState"
          :title="tripsState === 'empty' ? t('emp.trips.empty') : t('emp.loadError')"
          :message="tripsState === 'empty' ? t('emp.trips.emptyHint') : trips.state.error"
          :retry-label="t('common.retry')"
          @retry="trips.reload()"
        >
          <TripList :rows="tripPreview" />
          <Button
            class="emp-secondary-action"
            variant="outline"
            size="xl"
            :label="t('emp.trips.viewAll')"
            @click="router.push('/trips')"
          />
        </AsyncBoundary>
      </section>
    </div>

    <aside class="emp-fuel-commitment" aria-labelledby="emp-fuel-title">
      <span class="emp-commitment-kicker">{{ t("emp.today.nextAction") }}</span>
      <Icon name="fuel" :size="28" />
      <h2 id="emp-fuel-title">{{ t("emp.fuel.formTitle") }}</h2>
      <p>{{ t("emp.fuel.cardHint") }}</p>

      <div v-if="fuelRequests.state.status === 'loading'" class="emp-line-pulse" aria-hidden="true" />
      <LoadError
        v-else-if="fuelRequests.state.status === 'error'"
        :title="t('emp.loadError')"
        :detail="fuelRequests.state.error"
        :hint="t('emp.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="fuelRequests.reload()"
      />
      <div v-else class="emp-latest-fuel">
        <template v-if="latestFuelRequest">
          <span>{{ t("emp.fuel.lastRequest") }}</span>
          <strong>
            <bdi>{{ latestFuelRequest.litres }}</bdi> {{ t("emp.fuel.litresUnit") }}
          </strong>
          <span>
            <bdi v-if="latestFuelRequest.date">{{ formatDate(latestFuelRequest.date, lang) }}</bdi>
            <Badge
              :theme="fuelMeta(latestFuelRequest.statusKey).theme"
              size="md"
              :label="t(fuelMeta(latestFuelRequest.statusKey).key)"
            />
          </span>
        </template>
        <span v-else>{{ t("emp.fuel.historyEmpty") }}</span>
      </div>

      <p v-if="pendingFuelCount" class="emp-pending-note">
        {{ t("emp.fuel.pendingCount") }} <bdi>{{ formatInt(pendingFuelCount, lang) }}</bdi>
      </p>

      <Button
        class="emp-primary-action"
        variant="solid"
        theme="green"
        size="xl"
        :label="t('emp.fuel.newRequest')"
        @click="router.push('/fuel')"
      >
        <template #prefix><Icon name="send" :size="18" /></template>
      </Button>
    </aside>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Badge, Button } from "frappe-ui";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import LoadError from "@shared/components/LoadError.vue";
import VehicleFacts from "@shared/components/VehicleFacts.vue";

import Icon from "../Icon.vue";
import TripList from "../components/TripList.vue";
import { formatDate, formatInt } from "../fmt.js";
import { fuelMeta, vehicleMeta } from "../statusMeta.js";
import { useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t, lang } = useI18n();

const router = useRouter();
const { vehicle, trips, fuelRequests, latestFuelRequest, pendingFuelCount } = useEmployee();

const vehicleFacts = computed(() => {
  const v = vehicle.state.data || {};
  return [
    {
      key: "odometer",
      label: t("emp.vehicle.odometer"),
      value: formatInt(v.odometerKm, lang),
      suffix: t("emp.vehicle.kmUnit"),
      numeric: true,
    },
    {
      key: "registration",
      label: t("emp.vehicle.registration"),
      value: v.registrationExpiry
        ? `${t("emp.vehicle.validUntil")} ${formatDate(v.registrationExpiry, lang)}`
        : "",
    },
  ];
});

const vehicleState = computed(() => {
  if (vehicle.state.status === "loading" || vehicle.state.status === "idle") return "loading";
  if (vehicle.state.status === "error") return "error";
  return vehicle.state.data ? "ready" : "empty";
});

const tripsState = computed(() => {
  if (trips.state.status === "loading" || trips.state.status === "idle") return "loading";
  if (trips.state.status === "error") return "error";
  return trips.state.data.length ? "ready" : "empty";
});

const tripPreview = computed(() => {
  const openTrip = trips.state.data.find((trip) => trip.status !== "completed");
  return openTrip ? [openTrip] : trips.state.data.slice(0, 1);
});
</script>
