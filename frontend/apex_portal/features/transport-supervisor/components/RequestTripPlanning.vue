<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, FormControl, createListResource, createResource } from "frappe-ui";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { buildAdHocRequest } from "../assignmentState.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({ request: { type: Object, required: true } });
const emit = defineEmits(["saved"]);

const trips = createListResource({
  doctype: "Dispatch Trip",
  fields: ["name", "trip_title", "trip_date", "project", "status"],
  filters: { status: "Planned" },
  orderBy: "trip_date asc, planned_start asc, modified desc",
  pageLength: 50,
  auto: false,
});
const tripRecord = createResource({ url: "frappe.client.get", method: "GET", auto: false });
const assign = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
  method: "POST",
  auto: false,
});
const createAdHoc = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.create_ad_hoc_trip",
  method: "POST",
  auto: false,
});
const selectedTrip = ref("");
const pickupStop = ref("");
const dropoffStop = ref("");
const existingError = ref("");
const tripListError = ref("");
const adHocError = ref("");
const notice = ref("");
const tripStopsByName = reactive({});
const savingExisting = ref(false);
const savingAdHoc = ref(false);
let stopLoadGeneration = 0;
const pickupDateTime = String(props.request.pickup_datetime || "")
  .trim()
  .replace(" ", "T")
  .slice(0, 19);
const adHoc = reactive({
  trip_date: pickupDateTime.slice(0, 10),
  planned_start: pickupDateTime,
  planned_end: "",
});

const needsApproval = computed(() => props.request.status === "Validated");
const tripOptions = computed(() => [
  { label: __("Choose a Planned Trip"), value: "" },
  ...(trips.data || []).map((trip) => ({
    value: trip.name,
    label: trip.trip_title || `${trip.trip_date || __("trip")} · ${trip.project || trip.name}`,
  })),
]);
const stops = computed(() => tripStopsByName[selectedTrip.value] || []);
const stopOptions = computed(() => [
  { label: __("Choose a Stop"), value: "" },
  ...stops.value.map((stop) => ({ value: stop.stop_key, label: stop.stop_name || stop.stop_key })),
]);
// Both submits greyed on a compound condition and said nothing, so a supervisor who had filled
// three of four fields could not tell which one was still missing. The reason is the single source
// of truth: `can*` is its negation, so a live button and a rendered reason cannot both be true.
const assignReason = computed(() => {
  if (!selectedTrip.value) return __("Choose the planned trip first.");
  if (!pickupStop.value) return __("Specify the actual pickup stop.");
  if (!dropoffStop.value) return __("Specify the actual dropoff stop.");
  if (pickupStop.value === dropoffStop.value) return __("Choose two different stops for pickup and dropoff.");
  return "";
});
const createReason = computed(() => {
  if (!adHoc.trip_date) return __("Specify the trip date.");
  if (!adHoc.planned_start) return __("Specify the start time.");
  if (!adHoc.planned_end) return __("Specify the end time.");
  return "";
});
const canAssign = computed(() => !assignReason.value);
const canCreate = computed(() => !createReason.value);

async function loadTrips() {
  tripListError.value = "";
  try {
    await trips.reload();
  } catch (reason) {
    tripListError.value = safeErrorMessage(
      reason,
      __("Could not load the planned trips. Check the trips permission then try again."),
    );
  }
}

async function loadMoreTrips() {
  tripListError.value = "";
  const previousStart = trips.start;
  try {
    trips.update({ start: previousStart + trips.pageLength });
    await trips.list.fetch();
  } catch (reason) {
    trips.update({ start: previousStart });
    tripListError.value = safeErrorMessage(reason, __("Could not load more trips."));
  }
}

watch(selectedTrip, async (name) => {
  const generation = ++stopLoadGeneration;
  pickupStop.value = "";
  dropoffStop.value = "";
  existingError.value = "";
  if (!name) return;
  try {
    const result = await tripRecord.fetch({ doctype: "Dispatch Trip", name });
    if (generation !== stopLoadGeneration) return;
    tripStopsByName[name] = Array.isArray(result?.stops) ? result.stops : [];
    if (!stops.value.length) {
      existingError.value = __("The selected trip has no actual stops. Add the stops from the trip record first.");
    }
  } catch (reason) {
    if (generation !== stopLoadGeneration) return;
    existingError.value = safeErrorMessage(reason, __("Could not load the stops for the selected trip."));
  }
});

async function assignExisting() {
  if (!canAssign.value || savingExisting.value) return;
  existingError.value = "";
  notice.value = "";
  savingExisting.value = true;
  try {
    const result = await assign.submit({
      dispatch_trip: selectedTrip.value,
      transport_requests: JSON.stringify([{
        transport_request: props.request.name,
        pickup_stop: pickupStop.value,
        dropoff_stop: dropoffStop.value,
      }]),
    });
    notice.value = __("The request was assigned to the planned trip.");
    emit("saved", result);
  } catch (reason) {
    existingError.value = safeErrorMessage(reason, __("Could not assign. Check that the trip is planned and the request is approved."));
  } finally {
    savingExisting.value = false;
  }
}

async function createTrip() {
  if (!canCreate.value || savingAdHoc.value) return;
  adHocError.value = "";
  notice.value = "";
  savingAdHoc.value = true;
  try {
    const payload = buildAdHocRequest(props.request, adHoc);
    const result = await createAdHoc.submit({
      trip: JSON.stringify(payload.trip),
      transport_requests: JSON.stringify(payload.transport_requests),
    });
    notice.value = __("The custom trip was created and the request was assigned to it.");
    emit("saved", result);
  } catch (reason) {
    adHocError.value = safeErrorMessage(reason, __("Could not create the custom trip. Review the locations and times."));
  } finally {
    savingAdHoc.value = false;
  }
}

watch(needsApproval, (waitingForApproval, wasWaitingForApproval) => {
  if (!waitingForApproval && (wasWaitingForApproval !== false || !trips.data)) {
    void loadTrips();
  }
}, { immediate: true });
</script>

<template>
  <section class="supervisor-detail__section request-trip-planning">
    <header><h3>{{ __("Request Planning") }}</h3></header>
    <div v-if="needsApproval" class="feature-state request-trip-planning__approval" role="status">
      {{ __("Approve the request first from the \"Approve\" action below; assignment operations accept only approved or scheduled requests.") }}
    </div>
    <template v-else>
      <p v-if="notice" class="feature-success" role="status">{{ notice }}</p>
      <div class="request-trip-planning__grid">
        <form class="request-trip-planning__panel" @submit.prevent="assignExisting">
          <div><p class="feature-page__eyebrow">{{ __("Existing Trip") }}</p><h4>{{ __("Assign to a Planned Trip") }}</h4></div>
          <div v-if="tripListError" class="feature-error" role="alert">
            <p>{{ tripListError }}</p>
            <Button type="button" variant="outline" @click="loadTrips">{{ __("Reload Trips") }}</Button>
          </div>
          <FormControl v-model="selectedTrip" type="select" :label="__('Trip')" :options="tripOptions" required />
          <FormControl v-model="pickupStop" type="select" :label="__('Actual Pickup Stop')" :options="stopOptions" :disabled="!selectedTrip" :description="selectedTrip ? '' : __('Choose the trip first to see its stops.')" required />
          <FormControl v-model="dropoffStop" type="select" :label="__('Actual Dropoff Stop')" :options="stopOptions" :disabled="!selectedTrip" :description="selectedTrip ? '' : __('Choose the trip first to see its stops.')" required />
          <p v-if="existingError" class="feature-error" role="alert">{{ existingError }}</p>
          <p v-if="assignReason" class="feature-reason">{{ assignReason }}</p>
          <Button type="submit" theme="green" variant="solid" :loading="savingExisting" :disabled="!canAssign || savingExisting">{{ __("Assign to Trip") }}</Button>
          <Button v-if="trips.hasNextPage" type="button" variant="outline" :loading="trips.list.loading" @click="loadMoreTrips">{{ __("Load More Trips") }}</Button>
        </form>

        <form class="request-trip-planning__panel" @submit.prevent="createTrip">
          <div><p class="feature-page__eyebrow">{{ __("Custom Trip") }}</p><h4>{{ __("Create a Trip from the Request") }}</h4></div>
          <p>{{ __("The system creates an actual pickup and destination point from the request data, then assigns both together.") }}</p>
          <FormControl v-model="adHoc.trip_date" type="date" :label="__('Trip Date')" required />
          <FormControl v-model="adHoc.planned_start" type="datetime-local" :label="__('Start Time')" required />
          <FormControl v-model="adHoc.planned_end" type="datetime-local" :label="__('End Time')" required />
          <p v-if="adHocError" class="feature-error" role="alert">{{ adHocError }}</p>
          <p v-if="createReason" class="feature-reason">{{ createReason }}</p>
          <Button type="submit" theme="green" variant="solid" :loading="savingAdHoc" :disabled="!canCreate || savingAdHoc">{{ __("Create & Assign") }}</Button>
        </form>
      </div>
    </template>
  </section>
</template>
