<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import { computed } from "vue";
import Icon from "../components/Icon.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import { useI18n } from "../i18n";
import { useEmployee } from "../useEmployee.js";
import { metaFor } from "../tripMeta.js";

const { t, lang } = useI18n();
const { vehicle, trips, loading, loadError, reload } = useEmployee();

const tripPreview = computed(() => trips.value.slice(0, 2));

const AR_LOCALE = "ar-SA-u-nu-latn";
function fmtInt(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat(lang.value === "ar" ? AR_LOCALE : "en-US").format(n);
}

const statusMeta = {
  available: { cls: "pill-ok", key: "statusShort.available" },
  assigned: { cls: "pill-ok", key: "statusShort.assigned" },
  workshop: { cls: "pill-warn", key: "statusShort.workshop" },
  stopped: { cls: "pill-neutral", key: "statusShort.stopped" },
  stolen: { cls: "pill-warn", key: "statusShort.stolen" },
};
const vehicleStatus = computed(() => statusMeta[vehicle.status] || statusMeta.available);
</script>

<template>
  <div class="emp-grid">
    <div class="emp-col">
      <section class="emp-card reveal d1">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="car" :size="17" /></span>
          <div class="emp-card-titles">
            <h3>{{ t("emp.vehicle.title") }}</h3>
            <p class="emp-hint">{{ t("emp.vehicle.hint") }}</p>
          </div>
        </header>

        <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
        <div v-else-if="loadError && vehicle.empty" class="emp-fail">
          <p>{{ t("emp.loadError") }}</p>
          <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
            <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
          </button>
        </div>
        <EmptyState v-else-if="vehicle.empty" :title="t('emp.vehicle.empty')">
          <template #icon><Icon name="car" :size="20" /></template>
        </EmptyState>
        <template v-else>
          <div class="emp-vehicle-hero">
            <span class="emp-plate">{{ vehicle.plate }}</span>
            <div class="emp-vinfo">
              <b>{{ vehicle.model }}</b>
              <span>{{ vehicle.office }}</span>
            </div>
            <span class="emp-pill" :class="vehicleStatus.cls">
              <span class="dot"></span>{{ t(vehicleStatus.key) }}
            </span>
          </div>

          <div class="emp-kv-row">
            <div class="emp-kv">
              <small>{{ t("emp.vehicle.odometer") }}</small>
              <b class="tnum">{{ fmtInt(vehicle.odometerKm) }} {{ t("emp.vehicle.kmUnit") }}</b>
            </div>
            <div class="emp-kv">
              <small>{{ t("emp.vehicle.registration") }}</small>
              <b>{{ vehicle.registrationExpiry ? t("emp.vehicle.validUntil", { date: vehicle.registrationExpiry }) : t("common.none") }}</b>
            </div>
          </div>
        </template>
      </section>

      <section class="emp-card reveal d2">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
          <div class="emp-card-titles">
            <h3>{{ t("emp.trips.title") }}</h3>
            <p class="emp-hint">{{ t("emp.trips.hint") }}</p>
          </div>
        </header>

        <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
        <div v-else-if="loadError && !trips.length" class="emp-fail">
          <p>{{ t("emp.loadError") }}</p>
          <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
            <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
          </button>
        </div>
        <EmptyState v-else-if="!trips.length" :title="t('emp.trips.empty')">
          <template #icon><Icon name="clipboard-list" :size="20" /></template>
        </EmptyState>
        <template v-else>
          <ul class="emp-trips">
            <li v-for="trip in tripPreview" :key="trip.id" class="emp-trip">
              <span class="emp-pill" :class="metaFor(trip.status).cls">
                <span class="dot"></span>{{ t(metaFor(trip.status).key) }}
              </span>
              <div class="emp-route">
                <b>{{ trip.title }}</b>
                <span>
                  <template v-if="trip.date">{{ trip.date }}</template>
                  <template v-if="trip.when"> · {{ trip.when }}</template>
                  <template v-if="trip.distanceKm"> · {{ t("emp.trips.distance", { n: fmtInt(trip.distanceKm) }) }}</template>
                </span>
              </div>
              <span class="emp-arrow"><Icon name="chevron" :size="17" /></span>
            </li>
          </ul>
          <router-link to="/trips" class="emp-btn emp-btn-ghost">
            {{ t("emp.trips.viewAll") }}
          </router-link>
        </template>
      </section>
    </div>

    <section class="emp-card reveal d3">
      <header class="emp-card-head">
        <span class="emp-ic"><Icon name="fuel" :size="17" /></span>
        <div class="emp-card-titles">
          <h3>{{ t("emp.fuel.title") }}</h3>
          <p class="emp-hint">{{ t("emp.fuel.hint") }}</p>
        </div>
      </header>
      <router-link to="/fuel" class="emp-btn emp-btn-primary">
        <Icon name="fuel" :size="17" />{{ t("emp.nav.fuel") }}
      </router-link>
    </section>
  </div>
</template>
