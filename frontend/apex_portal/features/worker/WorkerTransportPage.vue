<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { ErrorMessage, createResource, toast } from "frappe-ui";
import { errorStatus, safeErrorMessage } from "../../core/errorMessage.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";
import WorkerBoardingPanel from "./WorkerBoardingPanel.vue";
import WorkerUpcomingTrips from "./WorkerUpcomingTrips.vue";
import WorkerPastTrips from "./WorkerPastTrips.vue";
import { __ } from "../../core/i18n.js";

const gateway = inject("workerGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const transportResource = createResource({
  url: "apex.salis.api.masar.get_worker_transport",
  method: "GET",
  auto: false,
});
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.worker_trip_boarding",
  method: "GET",
  auto: false,
});
const contextResource = createResource({
  url: "apex.salis.api.masar.get_worker_context",
  method: "GET",
  auto: false,
});
const state = ref("loading");
const transport = ref({ upcoming: [], past: [] });
const boarding = ref(null);
const error = ref(null);
const busy = ref("");
const now = ref(Date.now());
let pollTimer;
let clockTimer;
let activeRoom = "";
let unsubscribers = [];

const trips = computed(() => transport.value?.upcoming || []);
const pastTrips = computed(() => transport.value?.past || []);
const hasContent = computed(() => trips.value.length || pastTrips.value.length || boarding.value?.dispatch_trip);

function markRated(trip) {
  trip.has_rated = true;
}

function stopLive() {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  pollTimer = undefined;
  clockTimer = undefined;
  while (unsubscribers.length) unsubscribers.pop()();
  activeRoom = "";
}

function startLive(room, seconds) {
  if (room && room !== activeRoom) {
    while (unsubscribers.length) unsubscribers.pop()();
    activeRoom = room;
    for (const event of ["driver_trip_update", "boarding_update", "boarding_confirmed", "boarding_unmarked", "boarding_arrived"]) {
      unsubscribers.push(subscribe(room, event, () => load(true)) || (() => {}));
    }
  }
  clearInterval(pollTimer);
  if (boarding.value?.dispatch_trip && !["Boarded", "Absent"].includes(boarding.value.status)) {
    pollTimer = setInterval(() => load(true), Math.max(Number(seconds) || 10, 5) * 1000);
  }
}

async function load(quiet = false) {
  if (!quiet) state.value = "loading";
  error.value = null;
  try {
    const [transportData, boardingData, context] = await Promise.all([transportResource.fetch(), boardingResource.fetch(), contextResource.fetch()]);
    transport.value = transportData || { upcoming: [], past: [] };
    boarding.value = boardingData || null;
    state.value = hasContent.value ? "ready" : "empty";
    startLive(context?.realtime_room || "", boarding.value?.poll_seconds);
  } catch (reason) {
    if (quiet) return;
    state.value = [401, 403].includes(errorStatus(reason)) ? "denied" : "error";
    error.value = reason;
  }
}

async function run(key, action, message) {
  busy.value = key;
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

onMounted(() => {
  clockTimer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  load();
});
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page journey-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div>
        <p class="feature-page__eyebrow">{{ __("Masar trips") }}</p>
        <h2>{{ __("Your trip from the door to the seat") }}</h2>
        <p>{{ __("Track the bus arrival, ask the driver to wait, then confirm your boarding.") }}</p>
      </div>
    </header>

    <PortalSkeleton v-if="state === 'loading'" :rows="2" :label="__('Loading the trip')" />
    <PortalErrorState v-else-if="state === 'denied'" :title="__('Could not open the trips')" :message="error" :fallback="__('This section is not available for your account.')" @retry="load()" />
    <PortalErrorState v-else-if="state === 'error'" :title="__('Could not load the trips')" :message="error" :fallback="__('Could not load the trips.')" @retry="load()" />
    <div v-else-if="state === 'empty'" class="feature-state">
      <strong>{{ __("Your day is quiet") }}</strong>
      <p>{{ __("There is no trip scheduled for you right now.") }}</p>
    </div>

    <template v-else>
      <ErrorMessage v-if="error" :message="safeErrorMessage(error, __('Could not carry out the action.'))" />
      <WorkerBoardingPanel
        v-if="boarding?.dispatch_trip"
        :boarding="boarding"
        :now="now"
        :busy="busy"
        @wait="run('wait', gateway.requestWait, __('The wait request reached the driver'))"
        @confirm="run('boarded', gateway.claimBoarded, __('Your boarding has been recorded'))"
      />
      <WorkerUpcomingTrips :trips="trips" @error="error = $event" />
      <WorkerPastTrips :trips="pastTrips" @error="error = $event" @rated="markRated" />
    </template>
  </section>
</template>
