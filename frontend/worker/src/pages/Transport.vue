<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <!-- [T-320] pull-to-refresh indicator (page scrolls with the window) -->
    <PullIndicator :distance="ptr.distance.value" :refreshing="ptr.refreshing.value" :threshold="ptr.THRESHOLD" />

    <h2 class="section-title">{{ t("transport.title") }}</h2>

    <!-- Stale note: shown only when the live read failed and we render the
         last-known cached snapshot (offline). -->
    <div v-if="isStale" class="stale-note">
      <Icon name="alert" :size="14" class="shrink-0" />
      <span>{{ t("common.stale") }}</span>
    </div>

    <template v-if="tr.loading && !td">
      <Skeleton :lines="4" />
      <Skeleton :lines="3" />
    </template>

    <!-- Error with NO cached fallback: a revoked/disabled token (PermissionError)
         or a server failure must surface, not show as a benign empty state. When a
         cached snapshot exists we render it (labelled stale) instead. -->
    <div v-else-if="tr.error && !td" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="tr.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="upcoming.length || past.length">
      <!-- Upcoming trips: the only ones Home's "next ride" can ever point at. -->
      <section v-for="trip in upcoming" :key="trip.transport_request" class="card card-pad space-y-3">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-extrabold leading-tight truncate">
              {{ trip.request_type ? tEnum("requestType", trip.request_type) : trip.transport_request }}
            </div>
            <div v-if="trip.pickup_point || trip.pickup_datetime" class="mt-0.5 text-sm text-muted">
              <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
              <span v-if="trip.depart_time || trip.pickup_datetime"> · <bdi>{{ trip.depart_time ? formatTime(trip.depart_time) : formatDateTime(trip.pickup_datetime) }}</bdi></span>
            </div>
          </div>
          <span v-if="trip.status" class="pill pill-accent shrink-0">{{ tEnum("transportStatus", trip.status) }}</span>
        </div>

        <!-- Trip progress bar (status stepper) -->
        <TripProgressBar :status="trip.trip_status" />

        <!-- Vehicle + driver -->
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

        <!-- The worker's OWN two points: where the shuttle collects HIM (his
             building) and where it is going (the route's drop-off). A worker is not
             the driver, so other buildings' housing pickups are never shown. -->
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

        <!-- Full-route deep link: opens Google Maps with every ordered stop chained
             as waypoints (the same route the driver navigates). Shown only when the
             backend resolved two-plus navigable stops into a directions URL. -->
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

        <!-- No planned route yet: an explicit state so the trip card is never a bare/inert card. -->
        <div v-else-if="!myPickup(trip) && !destination(trip)" class="text-sm text-muted">{{ t("transport.noRoutePlanned") }}</div>

        <!-- Live boarding flow for the soonest upcoming trip (the one being boarded
             next): on-the-bus claim, departing countdown, wait request, rejection
             re-claim, wrong-bus correction, and the full-screen boarding pass. -->
        <BoardingFlow
          v-if="trip === upcoming[0]"
          :trip="trip"
          :boarding="boardingState"
          :stale="boardingStale"
          @refresh="boardingResource.reload().catch(() => {})"
        />

        <!-- "I'm at the pickup": simple self-confirm for the OTHER upcoming trips
             (the active boarding flow above owns the soonest one). -->
        <div v-else class="space-y-2">
          <BoardingWindow v-if="!canConfirm(trip)" :window="trip.boarding_window" />
          <template v-else>
            <button
              v-if="!confirmedTrips[trip.transport_request]"
              class="btn btn-primary"
              style="width: auto; padding-inline: 18px"
              :disabled="boarding.loading && boardingFor === trip.transport_request"
              @click="confirmBoarding(trip)"
            >
              <Icon name="check" :size="18" />
              {{ boarding.loading && boardingFor === trip.transport_request ? t("transport.atPickupSending") : t("transport.atPickup") }}
            </button>
            <p v-else class="status-ok flex items-center gap-2 text-sm">
              <Icon name="check" :size="16" class="shrink-0" />
              {{ t("transport.atPickupDone") }}
            </p>
          </template>
          <p v-if="boardingError && boardingFor === trip.transport_request" class="text-sm text-danger mt-1">{{ boardingError }}</p>
        </div>
      </section>

      <!-- No upcoming trip, but past ones exist: say so explicitly so the screen
           agrees with Home ("No upcoming ride") instead of looking broken. -->
      <div v-if="!upcoming.length" class="card card-pad text-center">
        <p class="text-sm text-muted">{{ t("transport.empty") }}</p>
        <p class="text-xs text-muted mt-1">{{ t("transport.emptyHint") }}</p>
      </div>

      <!-- Past trips: a compact, de-emphasised history so a departed trip is
           never mistaken for the next ride. Collapsed by default. -->
      <section v-if="past.length" class="card card-pad space-y-3">
        <button class="flex w-full items-center gap-2" @click="showPast = !showPast">
          <Icon name="clock" :size="18" class="text-muted shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("transport.past") }}</span>
          <span class="pill pill-neutral shrink-0">{{ past.length }}</span>
          <Icon name="chevron" :size="18" class="text-muted shrink-0 ms-auto" :style="showPast ? 'transform: rotate(90deg)' : ''" />
        </button>
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

      <!-- Worker-initiated transport request + report a transport issue. -->
      <router-link to="/request-transport" class="btn btn-primary" style="text-decoration: none">
        <Icon name="route" :size="18" class="rtl-flip" /> {{ t("transport.requestNew") }}
      </router-link>
      <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
        <Icon name="plus" :size="18" /> {{ t("transport.reportIssue") }}
      </router-link>
    </template>

    <div v-else class="space-y-3">
      <!-- Wrong-bus correction can arrive even with no upcoming trip (the worker
           scanned a vehicle that isn't theirs) — surface it before the empty copy. -->
      <BoardingFlow
        v-if="boardingState && boardingState.wrong_bus"
        :trip="null"
        :boarding="boardingState"
        :stale="boardingStale"
      />
      <div class="card card-pad text-center space-y-3">
        <div>
          <p class="text-sm text-muted">{{ t("transport.empty") }}</p>
          <p class="text-xs text-muted mt-1">{{ t("transport.emptyHint") }}</p>
        </div>
        <!-- Even with no trip, the worker can request one. -->
        <router-link to="/request-transport" class="btn btn-primary" style="text-decoration: none">
          <Icon name="route" :size="18" class="rtl-flip" /> {{ t("transport.requestNew") }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onUnmounted } from "vue";
import { BOARDING_SETTLED, REQUEST } from "@shared/statusVocabularies";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import TripProgressBar from "../components/TripProgressBar.vue";
import TripRating from "../components/TripRating.vue";
import PullIndicator from "../components/PullIndicator.vue";
import BoardingFlow from "../components/BoardingFlow.vue";
import BoardingWindow from "../components/BoardingWindow.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatTime, formatDateTime } from "../utils/datetime";
import { TOKEN } from "../utils/token";
import { waLink } from "../utils/phone";
import { usePullToRefresh } from "../composables/usePullToRefresh";
import { cacheGet, cacheSet } from "../utils/cache";

const { t, tEnum } = useI18n();

// Last good payload cached so a network drop renders stale-but-labelled data
// instead of an empty/error screen (mirrors the driver portal pattern).
const CACHE_KEY = "get_worker_transport";
const staleTr = ref(null);
const tr = createResource({
  url: "apex.salis.api.masar.get_worker_transport",
  params: { token: TOKEN },
  auto: true,
  onSuccess: (r) => {
    staleTr.value = null;
    cacheSet(CACHE_KEY, r);
  },
  onError: () => {
    const cached = cacheGet(CACHE_KEY);
    if (cached) staleTr.value = cached;
  },
});

// [T-320] pull down at the top to refresh upcoming trips. reload() returns the
// fetch promise, so the spinner keeps spinning until the data lands.
const ptr = usePullToRefresh(() => tr.reload());

const errorMessage = computed(() => resourceErrorMessage(tr.error));

// Live data when present; otherwise the cached snapshot (offline). td drives the UI.
const td = computed(() => tr.data || staleTr.value?.data || null);
// True while showing cached data because the live read failed — drives the label.
const isStale = computed(() => !tr.data && !!staleTr.value);

// [T-537] upcoming vs past — the backend splits on the same now_datetime() pivot
// Home uses, so the trip Home shows as "next ride" is exactly upcoming[0].
// (Older payloads only had a flat `trips`; fall back to it as the upcoming list.)
const upcoming = computed(() => td.value?.upcoming || td.value?.trips || []);
const past = computed(() => td.value?.past || []);
const showPast = ref(false);

// A worker is not the driver: he sees only HIS pickup + the route destination,
// both scoped server-side. For an older cached payload that only carried the flat
// `stops` list, fall back to the first housing pickup / the last stop so a stale
// render still shows two sane points instead of the whole driver route.
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

// Live boarding state for the soonest trip (the server's worker_trip_boarding
// state machine). Drives the boarding flow component. Polled adaptively: fast
// (poll_seconds, ~10s) while a boarding window is active, off otherwise — the
// app-shell's slow ~45s poll already refreshes the trip list for idle workers.
// frappe-ui keeps the PREVIOUS payload when a reload fails, so without this flag a
// worker on weak signal would keep seeing a live-looking claim button and countdown
// built on a snapshot that may be minutes old.
const boardingStale = ref(false);
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.worker_trip_boarding",
  params: { token: TOKEN },
  auto: true,
  onSuccess: () => {
    boardingStale.value = false;
  },
  onError: () => {
    boardingStale.value = true;
  },
});
const boardingState = computed(() => boardingResource.data || null);

// An "active boarding window" = a trip exists and isn't a terminal state. While
// active, poll every poll_seconds; revert to no fast-poll when idle/Boarded.
const boardingActive = computed(() => {
  const b = boardingState.value;
  return !!(b && b.dispatch_trip && !BOARDING_SETTLED.includes(b.status));
});
const pollSeconds = computed(() => boardingState.value?.poll_seconds || 10);

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
    // frappe-ui's handleError rethrows even with an onError, so absorb the rejection
    // here — onError has already flagged the board stale.
    if (!document.hidden) boardingResource.reload().catch(() => {});
  }, seconds * 1000);
}
// Arm/disarm the fast poll as the window opens/closes; re-arm if the cadence
// changes. The hidden-tab guard in the tick keeps a backgrounded tab quiet.
watch(
  [boardingActive, pollSeconds],
  ([active, secs]) => {
    if (active) startBoardingPoll(secs);
    else stopBoardingPoll();
  },
  { immediate: true },
);
onUnmounted(stopBoardingPoll);

// Worker boarding self-confirm. The server resolves the worker from the token and
// writes the boarding event; this UI just records which trips the worker has
// already confirmed so the card flips to a done state. Keyed by transport_request
// so each card tracks its own state.
const confirmedTrips = reactive({});
const boardingFor = ref(null);
const boardingError = ref("");
const boarding = createResource({
  url: "apex.salis.api.masar.confirm_boarding",
  // Nothing boardable today answers {"trip": null} — a 200 that wrote no boarding row and
  // left the driver's manifest untouched. Flipping the card on the bare 200 told the
  // worker the driver had been told they were waiting. A re-confirm is different: it
  // carries dispatch_trip with created false, and that is a real confirmation.
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
  boarding.submit({ token: TOKEN, transport_request: trip.transport_request });
}
</script>

<style scoped>
.stale-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
</style>
