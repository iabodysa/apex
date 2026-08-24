<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, createListResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { maintenanceIssueOptions } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const form = reactive({
  room: "",
  issue_type: "Other",
  issue_description: "",
  priority: "Medium",
});
const error = ref("");
const roomError = ref("");
const loadedBuilding = ref("");
const requests = createListResource({ doctype: "Maintenance Request", auto: false });
const rooms = createListResource({
  doctype: "Room",
  fields: ["name", "room_number"],
  orderBy: "room_number asc, name asc",
  pageLength: 100,
  auto: false,
});
const roomOptions = computed(() =>
  loadedBuilding.value === building.value
    ? (rooms.data || []).map((row) => ({ label: row.room_number || row.name, value: row.name }))
    : [],
);
// The submit greys for four separate reasons and named none of them, so a form that looked filled
// in ended at a dead button. The first unmet step wins, in the order the form asks for them, and
// the button reads its disabled state from here so the two can never disagree.
const submitReason = computed(() => {
  if (rooms.list.loading) return __("Loading the building's rooms.");
  if (!building.value) return __("Select the building first.");
  if (!form.room) return __("Select the room.");
  if (!form.issue_description) return __("Type a description of the problem.");
  return "";
});
let roomLoadQueue = Promise.resolve();

async function loadAllRooms(value) {
  rooms.update({ filters: { building: value }, start: 0 });
  await rooms.reload();
  while (rooms.hasNextPage) {
    rooms.update({ start: rooms.start + rooms.pageLength });
    await rooms.list.fetch();
  }
}

watch(
  building,
  (value) => {
    form.room = "";
    loadedBuilding.value = "";
    roomError.value = "";
    if (!value) return;
    roomLoadQueue = roomLoadQueue.then(async () => {
      if (building.value !== value) return;
      try {
        await loadAllRooms(value);
        if (building.value === value) loadedBuilding.value = value;
      } catch (exception) {
        if (building.value === value) {
          roomError.value = safeErrorMessage(exception, __("Could not load the building's rooms."));
        }
      }
    });
  },
  { immediate: true },
);
async function submit() {
  error.value = "";
  try {
    const result = await requests.insert.submit({ building: building.value, ...form });
    toast.create({
      type: "success",
      message: result?.name ? __("Maintenance request {0} was registered", [result.name]) : __("The maintenance request was registered"),
    });
    Object.assign(form, {
      room: "",
      issue_type: "Other",
      issue_description: "",
      priority: "Medium",
    });
  } catch (exception) {
    error.value = safeErrorMessage(exception, __("Could not register the request."));
  }
}
</script>
<template>
  <section class="feature-page">
    <h2>{{ __("New Maintenance Request") }}</h2>
    <BuildingPicker />
    <form class="feature-form" @submit.prevent="submit">
      <ErrorMessage v-if="roomError" :message="roomError" />
      <FormControl v-model="form.room" type="select" :label="__('Room')" :options="roomOptions" required />
      <FormControl
        v-model="form.issue_type"
        type="select"
        :label="__('Problem Type')"
        :options="maintenanceIssueOptions()"
        required
      />
      <FormControl v-model="form.issue_description" type="textarea" :label="__('Problem Description')" required />
      <FormControl
        v-model="form.priority"
        type="select"
        :label="__('Priority')"
        :options="[
          { label: __('Low'), value: 'Low' },
          { label: __('Medium'), value: 'Medium' },
          { label: __('High'), value: 'High' },
          { label: __('Critical Priority'), value: 'Critical' },
        ]"
      />
      <ErrorMessage v-if="error" :message="error" />
      <p v-if="submitReason" class="feature-reason">{{ submitReason }}</p>
      <Button type="submit" theme="green" variant="solid" :loading="requests.insert.loading" :disabled="Boolean(submitReason)">{{ __("Submit Request") }}</Button>
    </form>
  </section>
</template>
