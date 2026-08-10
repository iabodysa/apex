<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <PullIndicator :distance="ptr.distance.value" :refreshing="ptr.refreshing.value" :threshold="ptr.THRESHOLD" />

    <template v-if="tr.loading && !td">
      <Skeleton :lines="4" />
      <Skeleton :lines="3" />
    </template>

    <LoadError
      v-else-if="tr.error && !td"
      :title="t('errors.loadError')"
      :detail="errorMessage"
      :hint="t('errors.retryHint')"
      :retry-label="t('common.retry')"
      @retry="tr.reload()"
    />

    <template v-else-if="upcoming.length || past.length">
      <section v-for="trip in upcoming" :key="trip.transport_request" class="card card-pad space-y-3">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-bold leading-tight truncate">
              {{ trip.request_type ? tEnum("requestType", trip.request_type) : trip.transport_request }}
            </div>
            <div v-if="trip.pickup_point || trip.pickup_datetime" class="mt-0.5 text-sm text-muted">
              <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
              <span v-if="trip.depart_time || trip.pickup_datetime"> · <bdi>{{ trip.depart_time ? formatTime(trip.depart_time) : formatDateTime(trip.pickup_datetime) }}</bdi></span>
            </div>
          </div>
          <StatusLabel
            v-if="trip.status"
            class="shrink-0"
            :label="tEnum('transportStatus', trip.status)"
            tone="accent"
          />
        </div>

        <TripProgressBar :status="trip.trip_status" />

        <div v-if="trip.vehicle || trip.driver" class="grid grid-cols-1 gap-3">
          <div v-if="trip.vehicle" class="flex items-center gap-2 text-sm">
            <Icon name="truck" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.vehicle") }}</span>
            <span class="ms-auto font-semibold">
              <bdi>{{ trip.vehicle.plate_number || trip.vehicle.name }}</bdi>
              <span v-if="trip.vehicle.vehicle_category" class="text-muted font-normal">· {{ trip.vehicle.vehicle_category }}</span>
            </span>
          </div>
          <div v-if="trip.driver" class="flex items-center gap-2 text-sm">
            <Icon name="user" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.driver") }}</span>
            <span class="ms-auto font-semibold">{{ trip.driver.full_name }}</span>
          </div>
          <div v-if="trip.driver && trip.driver.phone" class="grid grid-cols-2 gap-3">
            <a :href="'tel:' + trip.driver.phone" class="btn btn-primary" style="text-decoration: none">
              <Icon name="phone" :size="18" /> {{ t("common.call") }}
            </a>
            <a :href="waLink(trip.driver.phone)" target="_blank" rel="noopener" class="btn btn-accent" style="text-decoration: none">
              <Icon name="message" :size="18" /> {{ t("common.whatsapp") }}
            </a>
          </div>
        </div>

        <div v-if="myPickup(trip) || destination(trip)">
          <div class="field-label">{{ t("transport.yourTrip") }}</div>
          <ol class="space-y-2">
            <li v-if="myPickup(trip)" class="flex items-start gap-3">
              <span class="avatar h-6 w-6 text-xs shrink-0"
                    style="background: var(--c-primary); color: var(--c-primary-ink); border-radius: var(--radius-sm)">
                <Icon name="user" :size="13" />
              </span>
              <div class="min-w-0">
                <div class="font-semibold leading-tight">
                  {{ t("transport.yourPickup") }}
                  <span v-if="myPickup(trip).planned_time" class="text-muted font-normal">· <bdi>{{ formatTime(myPickup(trip).planned_time) }}</bdi></span>
                </div>
                <div v-if="myPickup(trip).pickup" class="text-sm text-muted">
                  {{ myPickup(trip).pickup.building_name || myPickup(trip).accommodation_building }}
                  <span v-if="myPickup(trip).pickup.city">, {{ myPickup(trip).pickup.city }}</span>
                </div>
                <div v-else-if="myPickup(trip).location" class="text-sm text-muted">{{ myPickup(trip).location }}</div>
              </div>
            </li>
            <li v-if="destination(trip)" class="flex items-start gap-3">
              <span class="avatar h-6 w-6 text-xs shrink-0"
                    style="background: var(--c-accent); color: var(--c-primary-ink); border-radius: var(--radius-sm)">
                <Icon name="route" :size="13" class="rtl-flip" />
              </span>
              <div class="min-w-0">
                <div class="font-semibold leading-tight">
                  {{ t("transport.destination") }}
                  <span v-if="destination(trip).planned_time" class="text-muted font-normal">· <bdi>{{ formatTime(destination(trip).planned_time) }}</bdi></span>
                </div>
                <div class="text-sm text-muted">
                  {{ destination(trip).location || destination(trip).stop_name }}
                </div>
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
          style="text-decoration: none"
        >
          <Icon name="route" :size="18" class="rtl-flip" /> {{ t("transport.openRoute") }}
        </a>

        <div v-else-if="!myPickup(trip) && !destination(trip)" class="text-sm text-muted">{{ t("transport.noRoutePlanned") }}</div>

        <BoardingFlow
          v-if="trip === upcoming[0]"
          :trip="trip"
          :boarding="boardingState"
          :stale="boardingStale"
          @refresh="refreshBoarding"
        />

        <div v-else class="space-y-2">
          <BoardingWindow v-if="!canConfirm(trip)" :window="trip.boarding_window" />
          <template v-else>
            <Button
              v-if="!confirmedTrips[trip.transport_request]"
              variant="solid"
              theme="green"
              size="xl"
              :disabled="boarding.loading && boardingFor === trip.transport_request"
              :loading="boarding.loading && boardingFor === trip.transport_request"
              :label="t('transport.atPickup')"
              @click="confirmBoarding(trip)"
            >
              <template #prefix><Icon name="check" :size="18" /></template>
            </Button>
            <p v-else class="status-ok flex items-center gap-2 text-sm">
              <Icon name="check" :size="16" class="shrink-0" />
              {{ t("transport.atPickupDone") }}
            </p>
          </template>
          <p v-if="boardingError && boardingFor === trip.transport_request" class="text-sm text-danger mt-1">{{ boardingError }}</p>
        </div>
      </section>

      <EmptyState v-if="!upcoming.length" :title="t('transport.empty')" :hint="t('transport.emptyHint')">
        <template #icon><Icon name="route" :size="22" class="rtl-flip" /></template>
      </EmptyState>

      <section v-if="past.length" class="card card-pad space-y-3">
        <Button variant="ghost" size="xl" :label="`${t('transport.past')} (${past.length})`" @click="showPast = !showPast">
          <template #prefix><Icon name="clock" :size="18" /></template>
          <template #suffix><Icon name="chevron" :size="18" :style="showPast ? 'transform: rotate(90deg)' : ''" /></template>
        </Button>
        <ul v-if="showPast" class="space-y-2">
          <li v-for="trip in past" :key="trip.transport_request" class="flex flex-col gap-2 text-sm border-b pb-3 last:border-0 last:pb-0">
            <div class="flex items-start gap-2">
              <Icon name="route" :size="16" class="text-muted shrink-0 mt-0.5 rtl-flip" />
              <div class="min-w-0 flex-1">
                <div class="font-semibold leading-tight truncate">
                  {{ trip.request_type ? tEnum("requestType", trip.request_type) : trip.transport_request }}
                </div>
                <div v-if="trip.pickup_point || trip.pickup_datetime" class="text-muted flex items-center justify-between">
                  <div>
                    <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
                    <span v-if="trip.depart_time || trip.pickup_datetime"> · <bdi>{{ trip.depart_time ? formatTime(trip.depart_time) : formatDateTime(trip.pickup_datetime) }}</bdi></span>
                  </div>
                  <span v-if="trip.has_rated" class="text-success text-xs font-medium flex items-center gap-1">
                    <Icon name="check" :size="14" /> {{ t("transport.rated") }}
                  </span>
                </div>
              </div>
            </div>

            <div v-if="trip.status === REQUEST.FULFILLED && trip.dispatch_trip && !trip.has_rated" class="mt-2">
              <TripRating :trip="trip" @rated="trip.has_rated = true" />
            </div>
          </li>
        </ul>
      </section>

      <ActionDock>
        <template #secondary>
          <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
            <Icon name="plus" :size="18" /> {{ t("transport.reportIssue") }}
          </router-link>
        </template>
        <template #primary>
          <router-link to="/request-transport" class="btn btn-primary" style="text-decoration: none">
            <Icon name="route" :size="18" class="rtl-flip" /> {{ t("transport.requestNew") }}
          </router-link>
        </template>
      </ActionDock>
    </template>

    <div v-else class="space-y-3">
      <BoardingFlow
        v-if="hasWrongBus"
        :trip="null"
        :boarding="boardingState"
        :stale="boardingStale"
      />
      <EmptyState :title="t('transport.empty')" :hint="t('transport.emptyHint')">
        <template #icon><Icon name="route" :size="22" class="rtl-flip" /></template>
        <template #action>
          <router-link to="/request-transport" class="btn btn-primary" style="text-decoration: none">
            <Icon name="route" :size="18" class="rtl-flip" /> {{ t("transport.requestNew") }}
          </router-link>
        </template>
      </EmptyState>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onUnmounted } from "vue";
import { BOARDING_SETTLED, REQUEST } from "@shared/statusVocabularies";
import { Button, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import TripProgressBar from "../components/TripProgressBar.vue";
import TripRating from "../components/TripRating.vue";
import PullIndicator from "../components/PullIndicator.vue";
import BoardingFlow from "../components/BoardingFlow.vue";
import BoardingWindow from "../components/BoardingWindow.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatTime, formatDateTime } from "../utils/datetime";
import { waLink } from "../utils/phone";
import { usePullToRefresh } from "../composables/usePullToRefresh";
import { useWorkerRealtime } from "../realtime.js";

const { t, tEnum } = useI18n();

const tr = createResource({
  url: "apex.salis.api.masar.get_worker_transport",
  auto: true,
});

const ptr = usePullToRefresh(() => tr.reload());

const errorMessage = computed(() => resourceErrorMessage(tr.error));

const td = computed(() => tr.data || null);

const upcoming = computed(() => td.value?.upcoming || td.value?.trips || []);
const past = computed(() => td.value?.past || []);
const showPast = ref(false);

function myPickup(trip) {
  if (trip.my_pickup) return trip.my_pickup;
  const stops = trip.stops || [];
  return stops.find((s) => s.accommodation_building) || stops[0] || null;
}
function destination(trip) {
  if (trip.destination) return trip.destination;
  const stops = trip.stops || [];
  if (!stops.length) return null;
  const last = stops[stops.length - 1];
  return last === myPickup(trip) ? null : last;
}

function canConfirm(trip) {
  const w = trip.boarding_window;
  return w ? !!w.can_confirm : true;
}

const boardingStale = ref(false);
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.worker_trip_boarding",
  auto: true,
  onSuccess: () => {
    boardingStale.value = false;
  },
  onError: () => {
    boardingStale.value = true;
  },
});
const boardingState = computed(() => boardingResource.data || null);

function refreshBoarding() {
  boardingResource.reload().catch(() => {});
}

useWorkerRealtime((event) => {
  refreshBoarding();
  if (event === "driver_trip_update") tr.reload().catch(() => {});
});

const boardingActive = computed(() => {
  const b = boardingState.value;
  return !!(b && b.dispatch_trip && !BOARDING_SETTLED.includes(b.status));
});
const pollSeconds = computed(() => boardingState.value?.poll_seconds || 10);

const hasWrongBus = computed(() => !!boardingState.value?.wrong_bus);

let boardingTimer = null;
function stopBoardingPoll() {
  if (boardingTimer) {
    clearInterval(boardingTimer);
    boardingTimer = null;
  }
}
function startBoardingPoll(seconds) {
  stopBoardingPoll();
  boardingTimer = setInterval(() => {
    if (!document.hidden) refreshBoarding();
  }, seconds * 1000);
}
watch(
  [boardingActive, pollSeconds],
  ([active, secs]) => {
    if (active) startBoardingPoll(secs);
    else stopBoardingPoll();
  },
  { immediate: true },
);
onUnmounted(stopBoardingPoll);

const confirmedTrips = reactive({});
const boardingFor = ref(null);
const boardingError = ref("");
const boarding = createResource({
  url: "apex.salis.api.masar.confirm_boarding",
  onSuccess: (data) => {
    const confirmed = !!(data && data.dispatch_trip);
    confirmedTrips[boardingFor.value] = confirmed;
    boardingError.value = confirmed ? "" : t("transport.atPickupFailed");
    if (!confirmed) tr.reload();
  },
  onError: (e) => {
    boardingError.value = resourceErrorMessage(e, "transport.atPickupFailed");
  },
});

function confirmBoarding(trip) {
  boardingFor.value = trip.transport_request;
  boardingError.value = "";
  boarding.submit({ transport_request: trip.transport_request });
}
</script>
