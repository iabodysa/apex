<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * HOME — my vehicle. The greeting band is the shell heading (App.vue); this
 * page shows the vehicle hero card (plate · model · status pill) with its
 * compliance facts (odometer, registration expiry), a two-row upcoming-trips
 * PREVIEW that links to the real /trips page, and a call-to-action card that
 * leads to the /fuel page.
 */
import { computed } from "vue";
import Icon from "../components/Icon.vue";
// [#a281] Direct path, never the "@shared/components" barrel (see App.vue).
import EmptyState from "@shared/components/EmptyState.vue";
import { useI18n } from "../i18n";
import { useEmployee } from "../useEmployee.js";
import { metaFor } from "../tripMeta.js";

const { t, lang } = useI18n();
const { vehicle, trips, loading, loadError, reload } = useEmployee();

// The preview shows the two most recent rows; the full list lives at /trips.
const tripPreview = computed(() => trips.value.slice(0, 2));

// Localized integer formatting: Arabic locale pinned to Latin digits
// (`-u-nu-latn`) so one numeral system is on screen — matches App.vue.
const AR_LOCALE = "ar-SA-u-nu-latn";
function fmtInt(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat(lang.value === "ar" ? AR_LOCALE : "en-US").format(n);
}

// Vehicle status → pill class + label (reuses the board's status vocabulary).
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
      <!-- MY VEHICLE -->
      <section class="emp-card reveal d1">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="car" :size="17" /></span>
          <div class="emp-card-titles">
            <h3>{{ t("emp.vehicle.title") }}</h3>
            <p class="emp-hint">{{ t("emp.vehicle.hint") }}</p>
          </div>
        </header>

        <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
        <!-- [#emp-fail] Failure BEFORE the empty state. `vehicle.empty` starts true and
             a broken load never clears it, so without this branch a failed request
             rendered as "no vehicle is assigned to you" — a driver WITH a vehicle was
             told they had none. Also gated on `empty` so a vehicle that did load still
             shows when only a sibling request failed. -->
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

      <!-- MY TRIPS — two-row preview; the full list is the /trips page. -->
      <section class="emp-card reveal d2">
        <header class="emp-card-head">
          <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
          <div class="emp-card-titles">
            <h3>{{ t("emp.trips.title") }}</h3>
            <p class="emp-hint">{{ t("emp.trips.hint") }}</p>
          </div>
        </header>

        <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
        <!-- Same [#emp-fail] rule: "the trips request broke" is not "you have no trips". -->
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

    <!-- FUEL — call to action into the real /fuel page. -->
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
