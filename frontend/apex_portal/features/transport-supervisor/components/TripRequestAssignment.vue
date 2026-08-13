<script setup>
import { computed, onMounted, ref } from "vue";
import { Button, FormControl, createListResource, createResource } from "frappe-ui";

const props = defineProps({
  trip: { type: Object, required: true },
});
const emit = defineEmits(["saved"]);

const requests = createListResource({
  doctype: "Transport Request",
  fields: [
    "name",
    "requester_name",
    "from_location",
    "to_location",
    "worker_count",
    "status",
    "assigned_to_trip",
  ],
  filters: { status: ["in", ["Approved", "Scheduled"]] },
  orderBy: "pickup_datetime asc, modified asc",
  pageLength: 100,
  auto: false,
});
const assign = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
  method: "POST",
  auto: false,
});
const requestName = ref("");
const pickupStop = ref("");
const dropoffStop = ref("");
const error = ref("");

const alreadyAssigned = computed(
  () => new Set((props.trip.assigned_requests || []).map((row) => row.transport_request)),
);
const requestOptions = computed(() => [
  { label: "اختر طلباً", value: "" },
  ...(requests.data || [])
    .filter((row) => !row.assigned_to_trip && !alreadyAssigned.value.has(row.name))
    .map((row) => ({
      value: row.name,
      label: [row.from_location, row.to_location].filter(Boolean).join(" إلى ") || row.requester_name || row.name,
    })),
]);
const stopOptions = computed(() => [
  { label: "اختر نقطة توقف", value: "" },
  ...(props.trip.stops || []).map((stop) => ({
    value: stop.stop_key,
    label: stop.stop_name || stop.stop_key,
  })),
]);
const canSubmit = computed(
  () => requestName.value && pickupStop.value && dropoffStop.value,
);

async function save() {
  if (!canSubmit.value) return;
  error.value = "";
  try {
    await assign.submit({
      dispatch_trip: props.trip.name,
      transport_requests: JSON.stringify([
        {
          transport_request: requestName.value,
          pickup_stop: pickupStop.value,
          dropoff_stop: dropoffStop.value,
        },
      ]),
    });
    requestName.value = "";
    pickupStop.value = "";
    dropoffStop.value = "";
    await requests.reload();
    emit("saved");
  } catch (reason) {
    error.value = reason?.message || "تعذّر إسناد الطلب.";
  }
}

onMounted(requests.reload);
</script>

<template>
  <section class="supervisor-detail__section supervisor-request-assignment">
    <header><h3>إضافة طلب إلى الرحلة</h3></header>
    <form class="supervisor-request-assignment__form" @submit.prevent="save">
      <FormControl v-model="requestName" type="select" label="طلب النقل" :options="requestOptions" required />
      <FormControl v-model="pickupStop" type="select" label="نقطة الصعود" :options="stopOptions" required />
      <FormControl v-model="dropoffStop" type="select" label="نقطة النزول" :options="stopOptions" required />
      <Button type="submit" theme="green" variant="solid" :loading="assign.loading" :disabled="!canSubmit">
        إسناد الطلب
      </Button>
    </form>
    <p v-if="error" class="feature-error" role="alert">{{ error }}</p>
    <p v-else-if="!requestOptions.slice(1).length" class="feature-state">لا توجد طلبات جاهزة للإسناد.</p>
  </section>
</template>
