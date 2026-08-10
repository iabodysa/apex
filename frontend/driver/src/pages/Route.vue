<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <p v-if="!singleTrip" class="-mt-2 text-sm text-soft">{{ t("route.subtitle") }}</p>

    <template v-if="singleTrip">
      <Skeleton v-if="tripRoute.loading && !tripData" :rows="2" />

      <LoadError
        v-else-if="tripRoute.error && !tripData"
        :title="t('errors.loadFailed')"
        :detail="tripErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="tripRoute.reload()"
      />

      <template v-else-if="tripData">
        <section class="card card-pad space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-bold leading-tight truncate">
                <bdi>{{ tripData.route_name || tripData.dispatch_trip }}</bdi>
              </div>
              <div class="mt-0.5 text-sm text-muted">
                <span v-if="tripData.depart_time">{{ t("route.departs") }} <bdi>{{ tripData.depart_time }}</bdi></span>
                <span v-if="tripData.vehicle"> · <bdi>{{ tripData.vehicle }}</bdi></span>
              </div>
            </div>
            <StatusLabel
              v-if="tripData.status"
              class="shrink-0"
              :label="te('tripStatus', tripData.status)"
              tone="accent"
            />
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
                <Checkbox
                  v-if="tripData.started && stop.route_stop"
                  class="stop-check shrink-0"
                  :model-value="!!stop.done"
                  :disabled="stopBusy === stop.route_stop"
                  :aria-label="stop.done ? t('route.stopUndo') : t('route.stopDone')"
                  @update:model-value="toggleStop(stop)"
                />
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
                    <StatusLabel v-if="stop.arrived" class="ms-2" :label="t('route.arrived')" tone="success" />
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
                  <Button
                    v-if="tripData.started && stop.route_stop"
                    type="button"
                    class="arrive-btn"
                    variant="outline"
                    size="lg"
                    :disabled="arriveBusy === stop.route_stop"
                    :loading="arriveBusy === stop.route_stop"
                    :label="stop.arrived ? t('route.markNotArrived') : t('route.markArrived')"
                    @click="toggleArrived(stop)"
                  >
                    <template #prefix><Icon name="bus" :size="16" class="rtl-flip" /></template>
                  </Button>
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

          <EmptyState v-else :title="t('route.noRoutePlanned')" :hint="t('route.noRoutePlannedHint')">
            <template #icon><Icon name="route" :size="22" /></template>
          </EmptyState>
        </section>
      </template>

      <EmptyState v-else :title="t('route.empty')">
        <template #icon><Icon name="route" :size="22" /></template>
      </EmptyState>
    </template>

    <template v-else>
      <Skeleton v-if="route.loading && !routeData" :rows="3" />

      <LoadError
        v-else-if="route.error && !routeData"
        :title="t('errors.loadFailed')"
        :detail="routeErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="route.reload()"
      />

      <template v-else-if="routeData && routeData.trips && routeData.trips.length">
        <section v-for="trip in routeData.trips" :key="trip.dispatch_trip" class="card card-pad space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-bold leading-tight truncate">
                <bdi>{{ trip.dispatch_trip }}</bdi>
              </div>
              <div class="mt-0.5 text-sm text-muted">
                <span v-if="trip.depart_time">{{ t("route.departs") }} <bdi>{{ trip.depart_time }}</bdi></span>
                <span v-if="trip.vehicle"> · <bdi>{{ trip.vehicle }}</bdi></span>
              </div>
            </div>
            <StatusLabel
              class="shrink-0"
              :label="t('route.expected', { n: trip.expected_count })"
              tone="accent"
            />
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

      <EmptyState v-else :title="t('route.empty')" :hint="t('route.emptyHint')">
        <template #icon><Icon name="route" :size="22" /></template>
      </EmptyState>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Button, Checkbox, createResource } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import StopStepper from "../components/StopStepper.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { pushToast } from "../toast";

const { t, te } = useI18n();

const props = defineProps({ trip: { type: String, default: null } });
const singleTrip = computed(() => !!props.trip);

const route = createResource({
  url: "apex.salis.api.driver_portal.my_worker_route_today",
});

const tripRoute = createResource({
  url: "apex.salis.api.driver_portal.my_trip_route",
  makeParams: () => ({ dispatch_trip: props.trip }),
});

watch(
  () => props.trip,
  (trip) => (trip ? tripRoute.fetch() : route.fetch()),
  { immediate: true },
);

const routeData = computed(() => route.data || null);
const tripData = computed(() => tripRoute.data || null);
const routeErrorMessage = computed(() => resourceErrorMessage(route.error, "errors.loadFailed"));
const tripErrorMessage = computed(() => resourceErrorMessage(tripRoute.error, "errors.loadFailed"));

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
  min-inline-size: var(--tap-min);
  min-block-size: var(--tap-min);
  display: grid;
  place-items: center;
}
</style>
