<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import { ref, onMounted } from "vue";
import Icon from "../components/Icon.vue";
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

const AR_LOCALE = "ar-SA-u-nu-latn";
function fmtInt(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat(lang.value === "ar" ? AR_LOCALE : "en-US").format(n);
}
</script>

<template>
  <div class="emp-narrow">
    <section class="emp-card reveal d1">
      <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
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
