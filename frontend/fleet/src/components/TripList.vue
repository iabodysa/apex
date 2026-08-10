<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ol class="emp-trips">
    <li v-for="(trip, index) in rows" :key="trip.id" class="emp-trip">
      <span class="emp-trip-sequence tnum" aria-hidden="true">
        <bdi>{{ String(index + 1).padStart(2, "0") }}</bdi>
      </span>
      <div class="emp-route">
        <strong><bdi>{{ trip.title }}</bdi></strong>
        <span>
          <bdi v-if="trip.date">{{ formatDate(trip.date, lang) }}</bdi>
          <template v-if="trip.when"> · <bdi>{{ formatTime(trip.when, lang) }}</bdi></template>
          <template v-if="trip.distanceKm">
            · <bdi>{{ t("emp.trips.distance", { n: formatInt(trip.distanceKm, lang) }) }}</bdi>
          </template>
        </span>
      </div>
      <Badge
        class="emp-trip-status"
        :theme="tripMeta(trip.status).theme"
        size="md"
        :label="t(tripMeta(trip.status).key)"
      />
    </li>
  </ol>
</template>

<script setup>
import { Badge } from "frappe-ui";

import { formatDate, formatInt, formatTime } from "../fmt.js";
import { tripMeta } from "../statusMeta.js";
import { useI18n } from "@/i18n";

defineProps({
  rows: { type: Array, default: () => [] },
});

const { t, lang } = useI18n();
</script>
