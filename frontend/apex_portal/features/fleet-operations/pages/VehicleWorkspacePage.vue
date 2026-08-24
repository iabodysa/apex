<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, FormControl, createResource } from "frappe-ui";
import { actionAvailability, createSingleFlight } from "../state.js";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { __ } from "../../../core/i18n.js";

// What each fleet_os action accepts for the operator's text, read from its signature.
const NOTE_ARGUMENT = Object.freeze({
  stop: (note) => ({ reason: note }),
  workshopIn: (note) => ({ notes: note }),
  workshopOut: () => ({}),
  recover: () => ({}),
});
const route = useRoute(),
  vehicles = createResource({
    url: "apex.salis.api.fleet_os.get_fleet_os",
    method: "GET",
    auto: false,
  }),
  vehicleTimeline = createResource({
    url: "apex.salis.api.fleet_os.get_vehicle_timeline",
    method: "GET",
    auto: false,
  }),
  actions = Object.freeze({
    stop: createResource({
      url: "apex.salis.api.fleet_os.stop_vehicle",
      method: "POST",
      auto: false,
    }),
    workshopIn: createResource({
      url: "apex.salis.api.fleet_os.workshop_in",
      method: "POST",
      auto: false,
    }),
    workshopOut: createResource({
      url: "apex.salis.api.fleet_os.workshop_out",
      method: "POST",
      auto: false,
    }),
    recover: createResource({
      url: "apex.salis.api.fleet_os.recover",
      method: "POST",
      auto: false,
    }),
  }),
  vehicle = computed(() => {
    const list = vehicles.data?.vehicles || [];
    return list.find((v) => (v.name || v.plate) === route.params.vehicle) || null;
  }),
  timeline = computed(() => vehicleTimeline.data?.events || []),
  notice = ref(""),
  reason = ref(""),
  once = createSingleFlight();
const ACTION_LABEL = Object.freeze({
  stop: __("Stop the vehicle"),
  workshopIn: __("Workshop In"),
  workshopOut: __("Workshop Out"),
  recover: __("Return to Service"),
});
// A title attribute is invisible on the tablet these buttons are pressed on, so every
// refused action names itself and its reason beside the row.
const blockedActions = computed(() =>
  Object.keys(ACTION_LABEL)
    .map((name) => ({ name, ...actionAvailability(vehicle.value?.capabilities?.[name] || { allowed: true }) }))
    .filter((entry) => entry.disabled)
    .map((entry) => ({ ...entry, label: ACTION_LABEL[entry.name] })),
);
const isBlocked = (name) => blockedActions.value.some((entry) => entry.name === name);
async function load() {
  await Promise.all([vehicles.fetch(), vehicleTimeline.fetch({ plate: route.params.vehicle })]);
}
async function act(name) {
  const cap = vehicle.value?.capabilities?.[name] || {
    allowed: false,
    reason: __("This action is not available for this state."),
  };
  const state = actionAvailability(cap);
  if (state.disabled) {
    notice.value = state.reason;
    return;
  }
  // The four endpoints take different arguments on purpose: stop_vehicle reads a reason and maps
  // it to the Vehicle Suspension Select, workshop_in stores a free note, and workshop_out and
  // recover take neither. Sending one name to all four dropped the operator's text on three.
  const note = reason.value || undefined;
  const payload = { plate: route.params.vehicle, ...NOTE_ARGUMENT[name](note) };
  try {
    await once(`${name}:${route.params.vehicle}`, () => actions[name].submit(payload));
  } catch (error) {
    notice.value = safeErrorMessage(error, __("Could not carry out the action. Try again."));
    return;
  }
  notice.value = __("The action was carried out");
  await load();
}
onMounted(load);
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>{{ __("Vehicle Workspace") }}</p>
        <h2>
          <bdi>{{ vehicle?.plate || route.params.vehicle }}</bdi>
        </h2>
      </div>
      <Badge v-if="vehicle" :theme="statusTheme(vehicle.vehicle_status || vehicle.status)" :label="statusLabel(vehicle.vehicle_status || vehicle.status)" />
    </header>
    <PortalSkeleton v-if="vehicles.loading" :rows="3" :label="__('Loading the vehicle')" />
    <PortalErrorState v-else-if="vehicles.error" :title="__('Could not load the vehicle')" :message="vehicles.error" @retry="load" />
    <div v-else-if="!vehicle" class="ops-state ops-state--error">{{ __("The vehicle does not exist or is outside your project's scope.") }}</div>
    <div v-else class="ops-workspace">
      <main class="ops-panels">
        <article class="ops-card">
          <h3>{{ __("Status and Operation") }}</h3>
          <p>
            <bdi dir="auto">{{ vehicle.project || "—" }}</bdi> ·
            <bdi dir="auto">{{ vehicle.current_driver?.name_en || __("No representative assigned") }}</bdi>
          </p>
          <div class="ops-actions">
            <Button variant="outline" :label="__('OFF')" :disabled="isBlocked('stop')" @click="act('stop')" />
            <Button variant="outline" :label="__('Workshop In')" :disabled="isBlocked('workshopIn')" @click="act('workshopIn')" />
            <Button variant="outline" :label="__('Workshop Out')" :disabled="isBlocked('workshopOut')" @click="act('workshopOut')" />
            <Button variant="solid" theme="green" :label="__('Return to Service')" :disabled="isBlocked('recover')" @click="act('recover')" />
          </div>
          <ul v-if="blockedActions.length" class="ops-blocked-actions">
            <li v-for="entry in blockedActions" :key="entry.name">{{ entry.label }}: {{ entry.reason }}</li>
          </ul>
          <FormControl v-model="reason" type="textarea" :rows="2" :label="__('Action Note')" />
          <p class="ops-hint">{{ __("The note is saved only with Stop and Workshop In.") }}</p>
          <p v-if="notice" class="ops-reason">{{ notice }}</p>
        </article>
        <article class="ops-card">
          <h3>{{ __("Vehicle Compliance") }}</h3>
          <p>{{ statusLabel(vehicle.compliance_status || "Not Tracked") }}</p>
        </article>
        <article class="ops-card">
          <h3>{{ __("Recovery and Processing") }}</h3>
          <p>{{ __("Incident and cost decisions appear here from approved records.") }}</p>
        </article>
      </main>
      <aside class="ops-card">
        <h3>{{ __("Vehicle Timeline") }}</h3>
        <PortalSkeleton v-if="vehicleTimeline.loading" :rows="3" :label="__('Loading the timeline')" />
        <PortalErrorState
          v-else-if="vehicleTimeline.error"
          :title="__('Could not load the timeline')"
          :message="vehicleTimeline.error"
          @retry="vehicleTimeline.fetch({ plate: route.params.vehicle })"
        />
        <p v-else-if="!timeline.length" class="ops-state">{{ __("No events are recorded.") }}</p>
        <ol v-else>
          <li v-for="event in timeline" :key="`${event.kind}:${event.ref_name}`">
            <strong>{{ event.title }}</strong>
            <p>
              <bdi>{{ event.date }}</bdi>
            </p>
          </li>
        </ol>
      </aside>
    </div>
  </section>
</template>
