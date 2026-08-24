<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Button, FormControl, createListResource, createResource } from "frappe-ui";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { buildTripAssignments, meaningfulRequestTitle } from "../assignmentState.js";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { __ } from "../../../core/i18n.js";

const props = defineProps({ trip: { type: Object, required: true } });
const emit = defineEmits(["saved"]);

const requests = createListResource({
  doctype: "Transport Request",
  fields: [
    "name", "requester_name", "from_location", "to_location", "destination",
    "worker_count", "status", "assigned_to_trip",
  ],
  filters: { status: ["in", ["Approved", "Scheduled"]] },
  orderBy: "pickup_datetime asc, modified asc",
  pageLength: 50,
  auto: false,
});
const assign = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
  method: "POST",
  auto: false,
});
const selections = reactive({});
const error = ref("");
const loadError = ref("");
const saving = ref(false);

const alreadyAssigned = computed(
  () => new Set((props.trip.assigned_requests || []).map((row) => row.transport_request)),
);
const availableRequests = computed(() => (requests.data || [])
  .filter((row) => !row.assigned_to_trip && !alreadyAssigned.value.has(row.name)));
const selectedNames = computed(() => Object.keys(selections));
const stopKeys = computed(() => (props.trip.stops || []).map((stop) => stop.stop_key).filter(Boolean));
const stopOptions = computed(() => [
  { label: __("Choose a Stop"), value: "" },
  ...(props.trip.stops || []).map((stop) => ({
    value: stop.stop_key,
    label: stop.stop_name || stop.stop_key,
  })),
]);
// The count in the label moves while the button stays grey, so the supervisor reads the selection
// as the blocker when the real one is an unset stop on one row out of six. `canSubmit` is the
// reason's negation, so the button cannot be live while a reason is on screen.
const submitReason = computed(() => {
  if (!selectedNames.value.length) return __("Choose at least one request.");
  const rows = selectedNames.value.map((name) => selections[name]);
  if (rows.some((row) => !row?.pickup_stop || !row?.dropoff_stop)) {
    return __("Specify the pickup and dropoff stop for each selected request.");
  }
  if (rows.some((row) => row.pickup_stop === row.dropoff_stop)) {
    return __("Choose two different stops for pickup and dropoff in each request.");
  }
  return "";
});
const canSubmit = computed(() => !submitReason.value);

function toggleRequest(request, checked) {
  if (checked) {
    selections[request.name] = { pickup_stop: "", dropoff_stop: "" };
  } else {
    delete selections[request.name];
  }
}

async function loadRequests() {
  loadError.value = "";
  try {
    await requests.reload();
  } catch (reason) {
    loadError.value = safeErrorMessage(
      reason,
      __("Could not load the ready transport requests. Check the requests permission then try again."),
    );
  }
}

async function loadMoreRequests() {
  loadError.value = "";
  const previousStart = requests.start;
  try {
    requests.update({ start: previousStart + requests.pageLength });
    await requests.list.fetch();
  } catch (reason) {
    requests.update({ start: previousStart });
    loadError.value = safeErrorMessage(reason, __("Could not load more requests."));
  }
}

async function save() {
  if (!canSubmit.value || saving.value) return;
  error.value = "";
  saving.value = true;
  try {
    const transportRequests = buildTripAssignments(
      selectedNames.value,
      selections,
      stopKeys.value,
    );
    await assign.submit({
      dispatch_trip: props.trip.name,
      transport_requests: JSON.stringify(transportRequests),
    });
    selectedNames.value.forEach((name) => delete selections[name]);
    await loadRequests();
    emit("saved");
  } catch (reason) {
    error.value = safeErrorMessage(reason, __("Could not assign the requests. Review the request status and the trip stops."));
  } finally {
    saving.value = false;
  }
}

onMounted(loadRequests);
</script>

<template>
  <section class="supervisor-detail__section supervisor-request-assignment">
    <header><h3>{{ __("Assign Requests to the Trip") }}</h3><span>{{ selectedNames.length }}</span></header>
    <p class="feature-state">{{ __("Choose one or more requests and specify the actual pickup and dropoff stop for each request.") }}</p>
    <form class="supervisor-request-assignment__form" @submit.prevent="save">
      <!-- One chain, so the pending read cannot render beside the failure or beside the count.
           `fetched` turns true only after a request resolves without throwing
           (node_modules/frappe-ui/src/resources/resources.js:107), which is the difference
           between "no approved requests exist" and "we have not been told yet". -->
      <PortalSkeleton
        v-if="!requests.list.fetched && !loadError"
        :rows="3"
        :label="__('Loading Approved Requests')"
      />
      <div v-else-if="loadError" class="feature-error" role="alert">
        <p>{{ loadError }}</p>
        <Button type="button" variant="outline" @click="loadRequests">{{ __("Reload Requests") }}</Button>
      </div>
      <ul v-else-if="availableRequests.length" class="supervisor-request-assignment__list">
        <li v-for="request in availableRequests" :key="request.name">
          <label class="supervisor-request-assignment__choice">
            <FormControl
              type="checkbox"
              :model-value="Boolean(selections[request.name])"
              @update:model-value="toggleRequest(request, $event)"
            />
            <span class="record-identity">
              <strong dir="auto">{{ meaningfulRequestTitle(request) }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ request.name }}</bdi>
            </span>
            <small>{{ request.worker_count || 0 }} {{ __("passenger") }}</small>
          </label>
          <div v-if="selections[request.name]" class="supervisor-request-assignment__stops">
            <FormControl v-model="selections[request.name].pickup_stop" type="select" :label="__('Pickup Point')" :options="stopOptions" required />
            <FormControl v-model="selections[request.name].dropoff_stop" type="select" :label="__('Dropoff Point')" :options="stopOptions" required />
          </div>
        </li>
      </ul>
      <p v-else class="feature-state">{{ __("No approved requests ready for assignment.") }}</p>
      <p v-if="submitReason && availableRequests.length" class="feature-reason">{{ submitReason }}</p>
      <Button type="submit" theme="green" variant="solid" :loading="saving" :disabled="!canSubmit || saving">
        {{ __("Assign {0} Request", [selectedNames.length]) }}
      </Button>
      <Button
        v-if="requests.hasNextPage"
        type="button"
        variant="outline"
        :loading="requests.list.loading"
        @click="loadMoreRequests"
      >{{ __("Load More") }}</Button>
    </form>
    <p v-if="error" class="feature-error" role="alert">{{ error }}</p>
  </section>
</template>
