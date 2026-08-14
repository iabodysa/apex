<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Button, FormControl, createListResource, createResource } from "frappe-ui";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { buildTripAssignments, meaningfulRequestTitle } from "../assignmentState.js";

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
  { label: "اختر نقطة توقف", value: "" },
  ...(props.trip.stops || []).map((stop) => ({
    value: stop.stop_key,
    label: stop.stop_name || stop.stop_key,
  })),
]);
const canSubmit = computed(() => selectedNames.value.length > 0
  && selectedNames.value.every((name) => {
    const row = selections[name];
    return row?.pickup_stop && row?.dropoff_stop && row.pickup_stop !== row.dropoff_stop;
  }));

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
      "تعذّر تحميل طلبات النقل الجاهزة. تحقق من صلاحية الطلبات ثم أعد المحاولة.",
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
    loadError.value = safeErrorMessage(reason, "تعذّر تحميل طلبات إضافية.");
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
    error.value = safeErrorMessage(reason, "تعذّر إسناد الطلبات. راجع حالة الطلب ونقاط الرحلة.");
  } finally {
    saving.value = false;
  }
}

onMounted(loadRequests);
</script>

<template>
  <section class="supervisor-detail__section supervisor-request-assignment">
    <header><h3>إسناد طلبات إلى الرحلة</h3><span>{{ selectedNames.length }}</span></header>
    <p class="feature-state">اختر طلباً أو أكثر وحدد نقطة الصعود والنزول الفعلية لكل طلب.</p>
    <form class="supervisor-request-assignment__form" @submit.prevent="save">
      <div v-if="loadError" class="feature-error" role="alert">
        <p>{{ loadError }}</p>
        <Button type="button" variant="outline" @click="loadRequests">إعادة تحميل الطلبات</Button>
      </div>
      <ul v-if="availableRequests.length" class="supervisor-request-assignment__list">
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
            <small>{{ request.worker_count || 0 }} راكب</small>
          </label>
          <div v-if="selections[request.name]" class="supervisor-request-assignment__stops">
            <FormControl v-model="selections[request.name].pickup_stop" type="select" label="نقطة الصعود" :options="stopOptions" required />
            <FormControl v-model="selections[request.name].dropoff_stop" type="select" label="نقطة النزول" :options="stopOptions" required />
          </div>
        </li>
      </ul>
      <p v-else class="feature-state">لا توجد طلبات معتمدة جاهزة للإسناد.</p>
      <Button type="submit" theme="green" variant="solid" :loading="saving" :disabled="!canSubmit || saving">
        إسناد {{ selectedNames.length }} طلب
      </Button>
      <Button
        v-if="requests.hasNextPage"
        type="button"
        variant="outline"
        :loading="requests.list.loading"
        @click="loadMoreRequests"
      >تحميل المزيد</Button>
    </form>
    <p v-if="error" class="feature-error" role="alert">{{ error }}</p>
  </section>
</template>
