<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ul class="emp-trips">
    <!-- No chevron: there is no per-trip screen to open, and an affordance that leads nowhere
         teaches the reader that the interface lies. -->
    <li v-for="trip in rows" :key="trip.id" class="emp-trip">
      <Badge :theme="tripMeta(trip.status).theme" size="md" :label="t(tripMeta(trip.status).key)" />
      <div class="emp-route">
        <b>{{ trip.title }}</b>
        <span>
          <bdi v-if="trip.date">{{ trip.date }}</bdi>
          <template v-if="trip.when"> · <bdi>{{ trip.when }}</bdi></template>
          <template v-if="trip.distanceKm">
            · {{ t("emp.trips.distance", { n: formatInt(trip.distanceKm, lang) }) }}
          </template>
        </span>
      </div>
    </li>
  </ul>
</template>

<script setup>
import { Badge } from "frappe-ui";

import { formatInt } from "../fmt.js";
import { tripMeta } from "../statusMeta.js";
import { useI18n } from "@/i18n";

defineProps({
  rows: { type: Array, default: () => [] },
});

const { t, lang } = useI18n();
</script>
