<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ singleTrip ? t("route.tripTitle") : t("route.title") }}</h2>
    <p v-if="!singleTrip" class="-mt-2 text-sm text-soft">{{ t("route.subtitle") }}</p>

    <template v-if="singleTrip">
      <Skeleton v-if="tripRoute.loading && !tripData" :rows="2" />

      <ErrorState v-else-if="tripRoute.error && !tripData" :message="t('errors.loadFailed')" @retry="tripRoute.reload()" />

      <template v-else-if="tripData">
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

          <div v-if="tripData.has_route_plan && tripData.stops && tripData.stops.length">
            <StopStepper :stops="tripData.stops" />
            <div class="flex items-center justify-between">
              <div class="field-label">{{ t("route.stops") }}</div>
              <span v-if="tripData.started" class="text-xs text-muted">
                {{ t("route.stopsDone", { n: doneCount, m: tripData.stops.length }) }}
              </span>
            </div>
            <ol class="space-y-2">
              <li
                v-for="(stop, i) in tripData.stops"
                :key="stop.route_stop || i"
                class="flex items-start gap-3"
                :class="{ 'opacity-60': stop.done }"
              >
                <button
                  v-if="tripData.started && stop.route_stop"
                  class="stop-check shrink-0"
                  :class="{ 'is-done': stop.done }"
                  :disabled="stopBusy === stop.route_stop"
                  :aria-pressed="stop.done ? 'true' : 'false'"
                  :aria-label="stop.done ? t('route.stopUndo') : t('route.stopDone')"
                  @click="toggleStop(stop)"
                >
                  <Icon :name="stop.done ? 'badge' : 'route'" :size="14" />
                </button>
                <span
                  v-else
                  class="avatar h-6 w-6 text-xs shrink-0"
                  style="background: var(--c-primary); color: var(--c-primary-ink); border-radius: var(--radius-sm)"
                >
                  {{ stop.sequence || i + 1 }}
                </span>
                <div class="min-w-0">
                  <div class="font-semibold leading-tight" :class="{ 'line-through': stop.done }">
                    {{ stop.stop_name || t("route.stop") }}
                    <span v-if="stop.planned_time" class="text-muted font-normal">· <bdi>{{ stop.planned_time }}</bdi></span>
                    <span v-if="stop.arrived" class="pill pill-success ms-2">{{ t("route.arrived") }}</span>
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
                  <button
                    v-if="tripData.started && stop.route_stop"
                    type="button"
                    class="btn btn-outline arrive-btn"
                    :disabled="arriveBusy === stop.route_stop"
                    @click="toggleArrived(stop)"
                  >
                    <Icon name="bus" :size="16" class="rtl-flip" />
                    {{ stop.arrived ? t("route.markNotArrived") : t("route.markArrived") }}
                  </button>
                  <p v-if="tripData.started && stop.route_stop && !stop.arrived" class="text-xs text-muted mt-1">
                    {{ t("route.arrivedHint") }}
                  </p>
                </div>
              </li>
            </ol>

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

    <template v-else>
      <Skeleton v-if="route.loading && !routeData" :rows="3" />

      <ErrorState v-else-if="route.error && !routeData" :message="t('errors.loadFailed')" @retry="route.reload()" />

      <template v-else-if="routeData && routeData.trips && routeData.trips.length">
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
import { computed, ref, watch } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import StopStepper from "../components/StopStepper.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t } = useI18n();

const props = defineProps({ trip: { type: String, default: null } });
const singleTrip = computed(() => !!props.trip);

const route = createResource({
  url: "apex.salis.api.driver_portal.my_worker_route_today",
});

const tripRoute = createResource({
  url: "apex.salis.api.driver_portal.my_trip_route",
  makeParams: () => ({ dispatch_trip: props.trip }),
});

/* `/route` and `/route/:trip` are two records over ONE component, and vue-router renders the
   view unkeyed — so moving between them patches the same instance instead of remounting it.
   `auto` is read once when the resource is created, so whichever screen was opened first was
   the only one that ever fetched, and the other showed "no route" until a full reload.
   Fetching from a watcher makes the decision follow the parameter. */
watch(
  () => props.trip,
  (trip) => (trip ? tripRoute.fetch() : route.fetch()),
  { immediate: true },
);

const routeData = computed(() => route.data || null);
const tripData = computed(() => tripRoute.data || null);

const doneCount = computed(
  () => (tripData.value?.stops || []).filter((s) => s.done).length,
);
const stopBusy = ref(null);
const arriveBusy = ref(null);

const stopProgress = createResource({
  url: "apex.salis.api.driver_portal.mark_stop_progress",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

function applyProgress(map) {
  for (const row of tripData.value?.stops || []) {
    const state = map[row.route_stop];
    row.done = !!(state && state.done);
    row.done_at = state ? state.done_at : null;
    row.arrived = !!(state && state.arrived);
    row.arrived_at = state ? state.arrived_at : null;
  }
}

async function toggleStop(stop) {
  if (!stop.route_stop || stopBusy.value) return;
  stopBusy.value = stop.route_stop;
  const next = !stop.done;
  stop.done = next;
  try {
    const res = await stopProgress.submit({
      dispatch_trip: props.trip,
      route_stop: stop.route_stop,
      done: next ? 1 : 0,
      sequence: stop.sequence,
      stop_name: stop.stop_name,
    });
    applyProgress(res?.stop_progress || {});
  } catch (e) {
    stop.done = !next;
  } finally {
    stopBusy.value = null;
  }
}

/* The arrival flag is the only thing that lights the worker's "your driver has arrived"
   panel, and until now nothing in any portal wrote it. */
const arrival = createResource({
  url: "apex.salis.api.driver_portal.mark_arrived",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

async function toggleArrived(stop) {
  if (!stop.route_stop || arriveBusy.value) return;
  arriveBusy.value = stop.route_stop;
  const next = !stop.arrived;
  stop.arrived = next;
  try {
    const res = await arrival.submit({
      dispatch_trip: props.trip,
      route_stop: stop.route_stop,
      arrived: next ? 1 : 0,
      sequence: stop.sequence,
      stop_name: stop.stop_name,
    });
    applyProgress(res?.stop_progress || {});
    pushToast(next ? t("route.arrivedToast") : t("route.notArrivedToast"), "ok");
  } catch (e) {
    stop.arrived = !next;
  } finally {
    arriveBusy.value = null;
  }
}
</script>

<style scoped>
.arrive-btn {
  width: auto;
  min-height: var(--tap-min);
  padding-block: 8px;
  padding-inline: 14px;
  margin-block-start: 8px;
  font-size: var(--fs-sm);
}
.stop-check {
  position: relative;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  border: 2px solid var(--c-primary);
  background: transparent;
  color: var(--c-primary);
  transition: background 0.12s ease, color 0.12s ease;
}
.stop-check::after {
  content: "";
  position: absolute;
  inset: calc((var(--tap-min) - 24px) / -2);
}
.stop-check.is-done {
  background: var(--c-success);
  border-color: var(--c-success);
  color: var(--c-primary-ink);
}
.stop-check:disabled {
  opacity: 0.6;
}
</style>
