<script setup>
import { computed, inject, onBeforeUnmount, ref, watch } from "vue";
import { Button, ErrorMessage, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { RouterLink, useRoute } from "vue-router";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { bedAssignmentTarget, housingCandidateFromQuery } from "../arrivalFlow.js";
import { floorLabel, statusLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const route = useRoute();
const grid = createResource({
  url: "apex.habitat.api.front_desk.get_building_grid",
  makeParams: () => ({ building: building.value }),
});
const readiness = createResource({ url: "apex.habitat.api.front_desk.set_room_readiness" });
const error = ref("");
const canSetReadiness = (globalThis.window?.apex_portal?.capabilities || []).includes("set_readiness");
const rooms = computed(() => (grid.data?.floors || []).flatMap((floor) => floor.rooms.map((room) => ({ ...room, floor_label: floor.floor_label }))));
const candidate = computed(() => housingCandidateFromQuery(route.query));

const subscribeBuilding = inject("portalBuildingSubscribe", () => () => {});
let unsubscribers = [];
let liveBuilding = null;

function stopLive() {
  liveBuilding = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

function startLive(name) {
  if (name === liveBuilding) return;
  liveBuilding = name;
  while (unsubscribers.length) unsubscribers.pop()();
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => grid.fetch({ building: name })) || (() => {}));
}

watch(building, (value) => {
  if (value) grid.fetch();
  startLive(value);
}, { immediate: true });
onBeforeUnmount(stopLive);

async function setReady(room) {
  error.value = "";
  try {
    await readiness.submit({ room: room.room, status: "Ready" });
    toast.create({ type: "success", message: __("The room is ready") });
    await grid.fetch();
  } catch (exception) { error.value = safeErrorMessage(exception, __("Could not update the room readiness.")); }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>{{ __("Rooms & Beds") }}</h2><BuildingPicker /></header>
    <article v-if="candidate" class="selected-resident" aria-live="polite">
      <div><span>{{ __("Pick a Bed") }}</span><strong dir="auto">{{ candidate.label }}</strong><small v-if="candidate.project" dir="auto">{{ candidate.project }}</small></div>
      <RouterLink to="/arrivals">{{ __("Change Worker") }}</RouterLink>
    </article>
    <PortalSkeleton v-if="grid.loading && !grid.data" :rows="3" :label="__('Loading Beds')" />
    <ErrorMessage v-else-if="grid.error" :message="__('Could not load the beds.')" />
    <p v-else-if="!rooms.length && building" class="feature-page__empty">{{ __("No rooms in this building.") }}</p>
    <section v-for="room in rooms" :key="room.room" class="feature-card room-card">
      <header>
        <div>
          <strong><bdi dir="auto" translate="no">{{ room.room_number }}</bdi></strong>
          <small>
            {{ floorLabel(room.floor_label) }} · {{ room.room_type || __("room") }} ·
            {{ room.current_occupancy || 0 }} {{ __("of") }} {{ room.bed_capacity || room.beds.length }} ·
            {{ statusLabel(room.readiness_status) }}
          </small>
          <small v-if="room.dominant_project" dir="auto">{{ __("Dominant Project: {0}", [room.dominant_project]) }}</small>
        </div>
        <Button v-if="canSetReadiness && room.readiness_status !== 'Ready'" variant="subtle" :loading="readiness.loading" @click="setReady(room)">{{ __("Confirm Readiness") }}</Button>
      </header>
      <div class="bed-grid">
        <component
          :is="candidate && bed.occupant ? 'div' : RouterLink"
          v-for="bed in room.beds"
          :key="bed.bed"
          :to="candidate && bed.occupant ? undefined : bedAssignmentTarget(bed.bed, candidate)"
          :aria-disabled="candidate && bed.occupant ? 'true' : undefined"
          :data-state="bed.bed_color"
        >
          <strong><bdi dir="auto" translate="no">{{ bed.bed_code || bed.bed }}</bdi></strong>
          <small v-if="bed.occupant" dir="auto">{{ bed.occupant.employee_name }}</small>
          <small v-else>{{ candidate ? __("Choose This Bed") : __("Available") }}</small>
          <!-- An occupant's name is who is here, not why the tile refuses the tap the assignment
               flow just invited. With a candidate chosen the refusal has to say so itself. -->
          <small v-if="candidate && bed.occupant" class="bed-meta">{{ __("Occupied, cannot be assigned") }}</small>
          <small class="bed-meta">{{ statusLabel(bed.condition) }}<template v-if="bed.is_temporary"> · {{ __("Temporary") }}</template></small>
        </component>
      </div>
    </section>
    <ErrorMessage v-if="error" :message="error" />
  </section>
</template>
