<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ singleTrip ? t("route.tripTitle") : t("route.title") }}</h2>

    <!-- Single-trip drill-in (from a "My Trips" card): /route/:trip -->
    <template v-if="singleTrip">
      <LoadingState v-if="tripRoute.loading" :label="t('common.loading')" />

      <ErrorState v-else-if="tripRoute.error" :message="t('errors.loadFailed')" @retry="tripRoute.reload()" />

      <template v-else-if="tripRoute.data">
        <section class="card card-pad space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-extrabold leading-tight truncate">
                <bdi>{{ tripRoute.data.route_name || tripRoute.data.dispatch_trip }}</bdi>
              </div>
              <div class="mt-0.5 text-sm text-muted">
                <span v-if="tripRoute.data.depart_time">{{ t("route.departs") }} <bdi>{{ tripRoute.data.depart_time }}</bdi></span>
                <span v-if="tripRoute.data.vehicle"> · <bdi>{{ tripRoute.data.vehicle }}</bdi></span>
              </div>
            </div>
            <span v-if="tripRoute.data.status" class="pill pill-accent shrink-0">
              {{ tripRoute.data.status }}
            </span>
          </div>

          <!-- Trip with a route plan: render its ordered stops (the trip road) -->
          <div v-if="tripRoute.data.has_route_plan && tripRoute.data.stops && tripRoute.data.stops.length">
            <div class="field-label">{{ t("route.stops") }}</div>
            <ol class="space-y-2">
              <li
                v-for="(stop, i) in tripRoute.data.stops"
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
                    <span v-if="stop.planned_time" class="text-muted font-normal">· <bdi>{{ stop.planned_time }}</bdi></span>
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

          <!-- No route plan for this trip: explicit state, distinct from "no trips today" -->
          <div v-else class="text-center py-4">
            <div
              class="avatar mx-auto mb-2 h-11 w-11"
              style="background: color-mix(in srgb, var(--c-mint) 25%, transparent); color: var(--c-primary)"
            >
              <Icon name="route" :size="22" />
            </div>
            <p class="font-semibold">{{ t("route.noRoutePlanned") }}</p>
            <p class="text-sm text-muted">{{ t("route.noRoutePlannedHint") }}</p>
          </div>
        </section>
      </template>

      <EmptyState v-else :title="t('route.empty')" />
    </template>

    <!-- All-trips worker route (unchanged): /route -->
    <template v-else>
      <LoadingState v-if="route.loading" :label="t('common.loading')" />

      <ErrorState v-else-if="route.error" :message="t('errors.loadFailed')" @retry="route.reload()" />

      <template v-else-if="route.data && route.data.trips && route.data.trips.length">
        <section v-for="trip in route.data.trips" :key="trip.dispatch_trip" class="card card-pad space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-extrabold leading-tight truncate">
                <bdi>{{ trip.dispatch_trip }}</bdi>
              </div>
              <div class="mt-0.5 text-sm text-muted">
                <span v-if="trip.depart_time">{{ t("route.departs") }} <bdi>{{ trip.depart_time }}</bdi></span>
                <span v-if="trip.vehicle"> · <bdi>{{ trip.vehicle }}</bdi></span>
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
                    <span v-if="stop.planned_time" class="text-muted font-normal">· <bdi>{{ stop.planned_time }}</bdi></span>
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
                <span class="font-semibold"><bdi>{{ w.employee_name || w.employee }}</bdi></span>
                <span v-if="w.pickup_point" class="text-muted">· {{ w.pickup_point }}</span>
              </li>
            </ul>
          </div>
        </section>
      </template>

      <EmptyState v-else :title="t('route.empty')" :hint="t('route.emptyHint')" />
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

// `trip` route param (from /route/:trip) — present only on a per-trip drill-in.
const props = defineProps({ trip: { type: String, default: null } });
const singleTrip = computed(() => !!props.trip);

// All-trips worker route (unchanged) — only fetched when there's no :trip param.
const route = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_worker_route_today",
  auto: !singleTrip.value,
});

// Single trip's own ordered route — identity-scoped server-side to this driver.
const tripRoute = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trip_route",
  makeParams: () => ({ dispatch_trip: props.trip }),
  auto: singleTrip.value,
});
</script>
