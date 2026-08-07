<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * TRIPS — the full list behind the home page's two-row preview. Same
 * identity-scoped get_my_recent_trips endpoint, wider window (the endpoint
 * already takes days/limit server-side; the preview never passed them). The
 * page owns its own load state: the singleton's preview stays untouched, and
 * retry here re-fetches only this list.
 *
 * The empty state is a legitimate outcome, not a defect: a session user who is
 * no Salis Driver (an ordinary office employee) gets [] from the backend by
 * design and reads the same "no recent trips" copy the preview uses.
 */
import { ref, onMounted } from "vue";
import Icon from "../components/Icon.vue";
// [#a281] Direct path, never the "@shared/components" barrel (see App.vue).
import EmptyState from "@shared/components/EmptyState.vue";
import { useI18n } from "../i18n";
import { fetchTrips } from "../useEmployee.js";
import { metaFor } from "../tripMeta.js";

const { t, lang } = useI18n();

const trips = ref([]);
const loading = ref(true);
const loadError = ref(false);

async function load() {
  loading.value = true;
  loadError.value = false;
  try {
    trips.value = await fetchTrips();
  } catch (e) {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);

// Same Latin-digit pinning as App.vue / Home.vue: one numeral system on screen.
const AR_LOCALE = "ar-SA-u-nu-latn";
function fmtInt(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat(lang.value === "ar" ? AR_LOCALE : "en-US").format(n);
}
</script>

<template>
  <div class="emp-narrow">
    <!-- The page title + hint are the shell heading (App.vue), so the card
         carries only the list. -->
    <section class="emp-card reveal d1">
      <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
      <!-- [#emp-fail] Failure BEFORE the empty state: "the trips request broke"
           is not "you have no trips". -->
      <div v-else-if="loadError" class="emp-fail">
        <p>{{ t("emp.loadError") }}</p>
        <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="load">
          <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
        </button>
      </div>
      <EmptyState v-else-if="!trips.length" :title="t('emp.trips.empty')">
        <template #icon><Icon name="clipboard-list" :size="20" /></template>
      </EmptyState>
      <ul v-else class="emp-trips">
        <li v-for="trip in trips" :key="trip.id" class="emp-trip">
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
    </section>
  </div>
</template>
