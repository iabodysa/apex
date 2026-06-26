<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ singleTrip ? t("route.tripTitle") : t("route.title") }}</h2>
    <p v-if="!singleTrip" class="-mt-2 text-sm text-soft">{{ t("route.subtitle") }}</p>

    <!-- Single-trip drill-in (from a "My Trips" card): /route/:trip -->
    <template v-if="singleTrip">
      <Skeleton v-if="tripRoute.loading && !tripData" :rows="2" />

      <ErrorState v-else-if="tripRoute.error && !tripData" :message="t('errors.loadFailed')" @retry="tripRoute.reload()" />

      <template v-else-if="tripData">
        <div v-if="tripStale" class="stale-note">
          <Icon name="alert" :size="14" class="shrink-0" />
          <span>{{ t("offline.stale") }}</span>
        </div>
        <section class="card card-pad space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-extrabold leading-tight truncate">
                <bdi>{{ tripData.route_name || tripData.dispatch_trip }}</bdi>
              </div>
              <div class="mt-0.5 text-sm text-muted">
                <span v-if="tripData.depart_time">{{ t("route.departs") }} <bdi>{{ tripData.depart_time }}</bdi></span>
                <span v-if="tripData.vehicle"> · <bdi>{{ tripData.vehicle }}</bdi></span>
              </div>
            </div>
            <span v-if="tripData.status" class="pill pill-accent shrink-0">
              {{ tripData.status }}
            </span>
          </div>

          <!-- Trip with a route plan: render its ordered stops (the trip road) -->
          <div v-if="tripData.has_route_plan && tripData.stops && tripData.stops.length">
            <div class="field-label">{{ t("route.stops") }}</div>
            <ol class="space-y-2">
              <li
                v-for="(stop, i) in tripData.stops"
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

            <!-- One-tap navigation chaining every stop as ordered waypoints. -->
            <a
              v-if="tripData.maps_route_url"
              :href="tripData.maps_route_url"
              target="_blank"
              rel="noopener"
              class="btn btn-outline mt-3"
              style="width: auto; padding-inline: 16px"
            >
              <Icon name="map-pin" :size="16" /> {{ t("trips.fullRoute") }}
            </a>
          </div>

          <!-- Registered worker manifest with a one-tap call. -->
          <div v-if="tripData.workers && tripData.workers.length">
            <div class="field-label">{{ t("route.workers") }}</div>
            <ul class="space-y-1">
              <li
                v-for="(w, i) in tripData.workers"
                :key="i"
                class="flex items-center gap-2 text-sm"
              >
                <Icon name="user" :size="14" class="text-primary shrink-0" />
                <span class="font-semibold"><bdi>{{ w.employee_name || w.employee }}</bdi></span>
                <span v-if="w.pickup_point" class="text-muted">· {{ w.pickup_point }}</span>
                <a
                  v-if="w.phone"
                  :href="'tel:' + w.phone"
                  class="text-primary inline-flex items-center gap-1 ms-auto shrink-0"
                  :aria-label="t('route.callWorker')"
                >
                  <Icon name="phone" :size="16" />
                </a>
              </li>
            </ul>
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

    <!-- All-trips worker route: /route -->
    <template v-else>
      <Skeleton v-if="route.loading && !routeData" :rows="3" />

      <ErrorState v-else-if="route.error && !routeData" :message="t('errors.loadFailed')" @retry="route.reload()" />

      <template v-else-if="routeData && routeData.trips && routeData.trips.length">
        <div v-if="routeStale" class="stale-note">
          <Icon name="alert" :size="14" class="shrink-0" />
          <span>{{ t("offline.stale") }}</span>
        </div>
        <section v-for="trip in routeData.trips" :key="trip.dispatch_trip" class="card card-pad space-y-3">
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

          <!-- One-tap navigation chaining every stop as ordered waypoints. -->
          <a
            v-if="trip.maps_route_url"
            :href="trip.maps_route_url"
            target="_blank"
            rel="noopener"
            class="btn btn-outline"
            style="width: auto; padding-inline: 16px"
          >
            <Icon name="map-pin" :size="16" /> {{ t("trips.fullRoute") }}
          </a>

          <!-- Registered worker manifest with a one-tap call. -->
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
                <a
                  v-if="w.phone"
                  :href="'tel:' + w.phone"
                  class="text-primary inline-flex items-center gap-1 ms-auto shrink-0"
                  :aria-label="t('route.callWorker')"
                >
                  <Icon name="phone" :size="16" />
                </a>
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
import { computed, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { cacheGet, cacheSet } from "../cache";

const { t } = useI18n();

// `trip` route param (from /route/:trip) — present only on a per-trip drill-in.
const props = defineProps({ trip: { type: String, default: null } });
const singleTrip = computed(() => !!props.trip);

// Last good route payloads, cached so a network drop renders stale-but-labelled
// data instead of an error. Keyed per-trip so each drill-in keeps its own snapshot.
const ROUTE_KEY = "my_worker_route_today";
const tripKey = computed(() => `my_trip_route:${props.trip || ""}`);
const staleRoute = ref(null);
const staleTrip = ref(null);

// All-trips worker route (unchanged) — only fetched when there's no :trip param.
const route = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_worker_route_today",
  auto: !singleTrip.value,
  onSuccess: (r) => { staleRoute.value = null; cacheSet(ROUTE_KEY, r); },
  onError: () => { const c = cacheGet(ROUTE_KEY); if (c) staleRoute.value = c; },
});

// Single trip's own ordered route — identity-scoped server-side to this driver.
const tripRoute = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trip_route",
  makeParams: () => ({ dispatch_trip: props.trip }),
  auto: singleTrip.value,
  onSuccess: (r) => { staleTrip.value = null; cacheSet(tripKey.value, r); },
  onError: () => { const c = cacheGet(tripKey.value); if (c) staleTrip.value = c; },
});

// Live data when present, else the cached snapshot (offline). These drive the
// template; routeStale/tripStale flag when we're showing cached data.
const routeData = computed(() => route.data || staleRoute.value?.data || null);
const tripData = computed(() => tripRoute.data || staleTrip.value?.data || null);
const routeStale = computed(() => !route.data && !!staleRoute.value);
const tripStale = computed(() => !tripRoute.data && !!staleTrip.value);
</script>

<style scoped>
.stale-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg, #fef3c7);
  color: var(--c-warning, #92400e);
}
</style>
