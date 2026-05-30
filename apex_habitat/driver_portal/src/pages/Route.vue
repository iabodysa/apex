<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("route.title") }}</h2>

    <div v-if="route.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

    <template v-else-if="route.data && route.data.trips && route.data.trips.length">
      <section v-for="trip in route.data.trips" :key="trip.dispatch_trip" class="card card-pad space-y-3">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-extrabold leading-tight truncate">
              {{ trip.dispatch_trip }}
            </div>
            <div class="mt-0.5 text-sm text-muted">
              <span v-if="trip.depart_time">{{ t("route.departs") }} {{ trip.depart_time }}</span>
              <span v-if="trip.vehicle"> · {{ trip.vehicle }}</span>
            </div>
          </div>
          <span class="pill pill-accent shrink-0">
            {{ t("route.expected", { n: trip.expected_count }) }}
          </span>
        </div>

        <!-- Ordered stops (the trip road) -->
        <div v-if="trip.stops && trip.stops.length">
          <div class="field-label">{{ t("route.stops") }}</div>
          <ol class="space-y-2">
            <li
              v-for="(stop, i) in trip.stops"
              :key="i"
              class="flex items-start gap-3"
            >
              <span
                class="avatar h-6 w-6 text-xs shrink-0"
                style="background: var(--c-primary); color: var(--c-primary-ink); border-radius: var(--radius-sm)"
              >
                {{ stop.sequence || i + 1 }}
              </span>
              <div class="min-w-0">
                <div class="font-semibold leading-tight">
                  {{ stop.stop_name || t("route.stop") }}
                  <span v-if="stop.planned_time" class="text-muted font-normal">· {{ stop.planned_time }}</span>
                </div>
                <div v-if="stop.pickup" class="text-sm text-muted">
                  {{ stop.pickup.building_name || stop.accommodation_building }}
                  <span v-if="stop.pickup.city">, {{ stop.pickup.city }}</span>
                </div>
                <div v-else-if="stop.location" class="text-sm text-muted">{{ stop.location }}</div>
                <a
                  v-if="stop.pickup && stop.pickup.google_maps_url"
                  :href="stop.pickup.google_maps_url"
                  target="_blank"
                  rel="noopener"
                  class="text-primary text-sm inline-flex items-center gap-1 mt-0.5"
                >
                  <Icon name="external" :size="14" /> {{ t("route.openMap") }}
                </a>
              </div>
            </li>
          </ol>
        </div>

        <!-- Registered worker manifest -->
        <div v-if="trip.workers && trip.workers.length">
          <div class="field-label">{{ t("route.workers") }}</div>
          <ul class="space-y-1">
            <li
              v-for="(w, i) in trip.workers"
              :key="i"
              class="flex items-center gap-2 text-sm"
            >
              <Icon name="user" :size="14" class="text-primary shrink-0" />
              <span class="font-semibold">{{ w.employee_name || w.employee }}</span>
              <span v-if="w.pickup_point" class="text-muted">· {{ w.pickup_point }}</span>
            </li>
          </ul>
        </div>
      </section>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("route.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("route.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const route = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_worker_route_today",
  auto: true,
});
</script>
