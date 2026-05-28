<template>
  <div class="space-y-3">
    <h2 class="font-semibold">My Trips Today</h2>
    <div v-if="trips.loading" class="text-ah-forest/60">Loading…</div>
    <div v-else-if="!trips.data || !trips.data.length" class="text-ah-forest/60">No trips scheduled today.</div>
    <div v-for="t in trips.data" :key="t.name" class="bg-ah-surface rounded-xl p-3 shadow-sm">
      <div class="font-medium">{{ t.route_plan || t.name }}</div>
      <div class="text-sm text-ah-forest/60">
        Vehicle: {{ t.vehicle || "—" }} · {{ t.depart_time || "" }} → {{ t.return_time || "" }}
      </div>
      <div class="text-xs mt-1 inline-block px-2 py-0.5 rounded bg-ah-accent/30">{{ t.status }}</div>
    </div>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";

const trips = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trips_today",
  auto: true,
});
</script>
