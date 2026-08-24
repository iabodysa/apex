<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { Badge, ErrorMessage, createResource, toast } from "frappe-ui";
import { useRoute } from "vue-router";
import { statusLabel } from "../../core/displayLabels.js";
import { errorStatus, safeErrorMessage } from "../../core/errorMessage.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";
import DriverTripCommand from "./DriverTripCommand.vue";
import DriverStopsTimeline from "./DriverStopsTimeline.vue";
import DriverPassengerList from "./DriverPassengerList.vue";
import DriverScannerPanel from "./DriverScannerPanel.vue";
import { __ } from "../../core/i18n.js";

const route = useRoute();
const gateway = inject("driverGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const tripResource = createResource({
  url: "apex.salis.api.driver_portal.my_trip_route",
  method: "GET",
  auto: false,
});
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.get_trip_boarding",
  method: "GET",
  auto: false,
});
const todayResource = createResource({
  url: "apex.salis.api.driver_portal.personal.get_masar_today",
  method: "GET",
  auto: false,
});
const state = ref("loading");
const trip = ref(null);
const boarding = ref({ workers: [] });
const error = ref(null);
const busy = ref("");
const scanResult = ref("");
const now = ref(Date.now());
let pollTimer;
let clockTimer;
let unsubscribers = [];
let liveRoom = null;

const dispatchTrip = computed(() => route.params.trip);
const statusByEmployee = computed(() => new Map((boarding.value?.workers || []).map((worker) => [worker.employee, worker])));
const workers = computed(() =>
  (trip.value?.workers || []).map((worker) => ({
    ...worker,
    ...(statusByEmployee.value.get(worker.employee) || { status: "Pending", wait_count: 0 }),
  })),
);
const pendingWorkers = computed(() => workers.value.filter((worker) => worker.status !== "Boarded"));
// Counted here rather than in the template: the clock ticks every second, and a template
// expression would re-scan both lists on every tick.
const boardedCount = computed(() => workers.value.filter((worker) => worker.status === "Boarded").length);
const completedStops = computed(() => (trip.value?.stops || []).filter((stop) => stop.done).length);

const scanMessages = Object.freeze({
  Valid: __("Boarding has been recorded."),
  Duplicate: __("This boarding was already recorded."),
  "Wrong Trip": __("The pass belongs to a different trip."),
  Expired: __("The boarding pass has expired."),
  "Invalid Token": __("The boarding pass is not valid."),
});

function stopLive() {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  liveRoom = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

// Every poll calls this, so it must be a no-op while the room holds: tearing the five listeners
// down and rebuilding them every ten seconds also restarted the poll that called it.
function startLive(room) {
  if (room === liveRoom) return;
  liveRoom = room;
  while (unsubscribers.length) unsubscribers.pop()();
  if (room) {
    for (const event of ["boarding_update", "boarding_confirmed", "boarding_unmarked", "boarding_arrived", "wait_request"]) {
      unsubscribers.push(subscribe(room, event, () => load(true)) || (() => {}));
    }
  }
  clearInterval(pollTimer);
  pollTimer = setInterval(() => load(true), 10000);
}

async function load(quiet = false) {
  if (!quiet) state.value = "loading";
  error.value = null;
  try {
    const [tripData, boardingData, today] = await Promise.all([tripResource.fetch({ dispatch_trip: dispatchTrip.value }), boardingResource.fetch({ dispatch_trip: dispatchTrip.value }), todayResource.fetch()]);
    trip.value = tripData;
    boarding.value = boardingData || { workers: [] };
    state.value = tripData ? "ready" : "empty";
    startLive(today?.realtime_room || "");
  } catch (reason) {
    if (quiet) return;
    state.value = [401, 403].includes(errorStatus(reason)) ? "denied" : "error";
    error.value = reason;
  }
}

async function run(key, action, message) {
  busy.value = key;
  error.value = null;
  try {
    await action();
    toast.create({ type: "success", message });
    await load(true);
  } catch (reason) {
    error.value = reason;
  } finally {
    busy.value = "";
  }
}

async function submitScan(token) {
  if (!token) return;
  busy.value = "scan";
  try {
    const result = await gateway.scanPass(token);
    scanResult.value = scanMessages[result?.result] || __("Could not read the pass.");
    if (["Valid", "Duplicate"].includes(result?.result)) await load(true);
  } catch (reason) {
    scanResult.value = safeErrorMessage(reason, __("Could not record the boarding."));
  } finally {
    busy.value = "";
  }
}

onMounted(() => {
  clockTimer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  load();
});
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page journey-page driver-journey" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div>
        <p class="feature-page__eyebrow">{{ __("Trip Execution") }}</p>
        <h2>{{ trip?.route_name || __("Itinerary") }}</h2>
        <p>{{ __("Stops and passengers on one screen.") }}</p>
      </div>
      <Badge v-if="trip" :label="statusLabel(trip.status)" />
    </header>

    <PortalSkeleton v-if="state === 'loading'" :rows="3" :label="__('Preparing the trip')" />
    <PortalErrorState v-else-if="state === 'denied'" :title="__('Could not open the trip')" :message="error" :fallback="__('This trip is not available for your account.')" @retry="load()" />
    <PortalErrorState v-else-if="state === 'error'" :title="__('Could not load the trip')" :message="error" :fallback="__('Could not load the trip.')" @retry="load()" />
    <div v-else-if="state === 'empty'" class="feature-state">{{ __("There is no data for this trip.") }}</div>

    <template v-else>
      <ErrorMessage v-if="error" :message="safeErrorMessage(error, __('Could not carry out the action.'))" />
      <DriverTripCommand
        :boarded-count="boardedCount"
        :pending-count="pendingWorkers.length"
        :completed-stops="completedStops"
        :started="Boolean(trip.started)"
        :busy="busy"
        @start="run('start', () => gateway.startTrip(dispatchTrip), __('The trip has started'))"
        @finish="run('finish', () => gateway.finishTrip(dispatchTrip), __('The trip has ended'))"
      />

      <DriverStopsTimeline
        :stops="trip.stops"
        :started="Boolean(trip.started)"
        :busy="busy"
        :maps-route-url="trip.maps_route_url || ''"
        @arrive="(stop) => run(`arrive:${stop}`, () => gateway.arriveAtStop(dispatchTrip, stop), __('Those waiting have been notified of your arrival'))"
        @toggle="(stop, done) => run(`stop:${stop}`, () => gateway.setStopProgress(dispatchTrip, stop, !done), done ? __('The stop was returned to the route') : __('The stop was completed'))"
      />

      <DriverPassengerList
        :workers="workers"
        :busy="busy"
        :wait-limit="Number(boarding.worker_wait_request_max) || 0"
        :wait-window-seconds="Number(boarding.worker_wait_request_seconds) || 0"
        :now="now"
        :pending-count="pendingWorkers.length"
        :grace-elapsed="Boolean(boarding.grace_elapsed)"
        @manual-board="(employee) => run(`manual:${employee}`, () => gateway.manualBoard(dispatchTrip, employee), __('Boarding was recorded manually'))"
        @unmark="(employee) => run(`unmark:${employee}`, () => gateway.markNotBoarded(dispatchTrip, employee), __('The worker was returned to the waiting list'))"
        @notify="run('notify', () => gateway.notifyPassengers(dispatchTrip), __('The rest were notified'))"
        @depart="run('depart', () => gateway.depart(dispatchTrip), __('Boarding was closed and the bus departed'))"
      />

      <DriverScannerPanel :busy="busy" :result="scanResult" @scan="submitScan" @error="scanResult = $event" />
    </template>
  </section>
</template>
