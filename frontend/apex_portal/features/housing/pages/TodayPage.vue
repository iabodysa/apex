<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ErrorMessage, createResource } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building, selectBuilding } from "../building.js";
import { createSupervisorBuildingsResource } from "../data/buildings.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import { __ } from "../../../core/i18n.js";

const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canSeeBeds = capabilities.includes("estate_read");
const canSeeArrivals = capabilities.includes("check_in");
const canSeeMaintenance = capabilities.includes("maintenance_read");
const canCreateMaintenance = capabilities.includes("maintenance_create");
const canSeeCustody = capabilities.includes("custody_read");
const canSeeSafety = capabilities.includes("safety_read");
const canSeePortfolio = canSeeBeds;
const canSelectBuilding = canSeePortfolio || canSeeArrivals;
const buildings = canSeePortfolio ? createSupervisorBuildingsResource() : null;
const grid = createResource({ url: "apex.habitat.api.front_desk.get_building_grid" });
const requests = createResource({ url: "apex.habitat.api.front_desk.building_open_requests" });
const arrivals = createResource({ url: "apex.habitat.api.arrivals_desk.get_expected_arrivals" });
const safety = createResource({ url: "apex.habitat.api.safety_checklist.get_due_cadences" });
const error = ref("");
const visibleResources = computed(() => [
  canSeeBeds ? grid : null,
  canSeeMaintenance ? requests : null,
  canSeeArrivals ? arrivals : null,
  canSeeSafety ? safety : null,
].filter(Boolean));
const loading = computed(() => visibleResources.value.some((resource) => resource.loading));
const summary = computed(() => grid.data?.summary || {});
const availableBeds = computed(() => Number(summary.value.available || 0));
const occupiedBeds = computed(() => Number(summary.value.occupied || 0));
const unavailableBeds = computed(() => ["blocked", "out_of_service"]
  .reduce((total, key) => total + Number(summary.value[key] || 0), 0));
const dueRounds = computed(() => safety.data?.due?.length || 0);

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
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => load()) || (() => {}));
}

async function load() {
  error.value = "";
  if (!building.value) return;
  const jobs = [];
  if (canSeeBeds) jobs.push(grid.fetch({ building: building.value }));
  if (canSeeMaintenance) jobs.push(requests.fetch({ building: building.value }));
  if (canSeeArrivals) jobs.push(arrivals.fetch({ building: building.value }));
  if (canSeeSafety) jobs.push(safety.fetch({ building: building.value }));
  const results = await Promise.allSettled(jobs);
  if (results.some((result) => result.status === "rejected")) {
    error.value = __("Could not refresh part of today's board. You can continue with the rest of the visible tasks.");
  }
}

watch(building, load, { immediate: true });
watch(building, startLive, { immediate: true });
onMounted(() => {
  if (canSeePortfolio) buildings.fetch();
});
onBeforeUnmount(stopLive);
</script>
<template>
  <section class="feature-page today-page">
    <header class="feature-page__header arrivals-heading">
      <div><p class="feature-kicker">{{ __("Housing Shift") }}</p><h2>{{ __("What needs your attention today") }}</h2><p>{{ __("A quick snapshot of the building, then the nearest action.") }}</p></div>
      <BuildingPicker v-if="canSelectBuilding" :resource="buildings" />
    </header>

    <section v-if="canSeePortfolio" class="today-portfolio" aria-labelledby="today-portfolio-title">
      <header>
        <div><p class="feature-kicker">{{ __("Supervision Scope") }}</p><h3 id="today-portfolio-title">{{ __("Housing Buildings Readiness") }}</h3></div>
        <RouterLink to="/beds">{{ __("Open Rooms Board") }}</RouterLink>
      </header>
      <PortalSkeleton v-if="buildings.loading && !buildings.data" :rows="3" :label="__('Loading Housing Buildings')" />
      <PortalErrorState
        v-else-if="buildings.error"
        :title="__('Could not load the housing scope')"
        :message="buildings.error"
        @retry="buildings.fetch"
      />
      <p v-else-if="!buildings.data?.length" class="feature-page__empty">{{ __("No active buildings within your scope.") }}</p>
      <ul v-else class="today-portfolio__list">
        <li v-for="item in buildings.data" :key="item.building">
          <button type="button" :aria-pressed="building === item.building" @click="selectBuilding(item.building)">
            <span class="record-identity">
              <strong dir="auto">{{ item.building_title }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ item.building }}</bdi>
            </span>
            <span>{{ item.occupied }} {{ __("Occupied") }} · {{ item.available }} {{ __("Available") }} · {{ item.blocked + item.oos }} {{ __("Not Ready") }}</span>
            <small>{{ __("Total Occupancy Percent") }} {{ item.occupancy_pct }}٪</small>
          </button>
        </li>
      </ul>
    </section>

    <p v-if="!building" class="feature-page__empty">{{ __("Select the building to view today's tasks.") }}</p>
    <PortalSkeleton v-else-if="loading && !grid.data" :rows="3" :label="__('Loading Today\'s Tasks')" />
    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <div v-if="canSeeBeds || canSeeArrivals || canSeeMaintenance || canSeeSafety" class="today-metrics">
        <RouterLink v-if="canSeeBeds" to="/beds"><strong>{{ availableBeds }}</strong><span>{{ __("Bed Available") }}</span><small>{{ occupiedBeds }} {{ __("Occupied") }}, {{ unavailableBeds }} {{ __("Not Ready") }}</small></RouterLink>
        <RouterLink v-if="canSeeArrivals" to="/arrivals"><strong>{{ arrivals.data?.pending || 0 }}</strong><span>{{ __("Arrival Awaiting Reception") }}</span><small>{{ arrivals.data?.arrived || 0 }} {{ __("registered today") }}</small></RouterLink>
        <RouterLink v-if="canSeeMaintenance" to="/maintenance"><strong>{{ requests.data?.open_requests || 0 }}</strong><span>{{ __("Open Request") }}</span><small>{{ __("Maintenance and resident complaints") }}</small></RouterLink>
        <RouterLink v-if="canSeeSafety" to="/rounds"><strong>{{ dueRounds }}</strong><span>{{ __("Safety Round Due") }}</span><small>{{ safety.data?.awaiting?.length || 0 }} {{ __("Pending Approval") }}</small></RouterLink>
      </div>

      <section v-if="canSeeArrivals || canSeeBeds || canSeeCustody || canCreateMaintenance" class="today-actions" aria-labelledby="today-actions-title">
        <div><p class="feature-kicker">{{ __("Quick Actions") }}</p><h3 id="today-actions-title">{{ __("Start From the Task") }}</h3></div>
        <nav class="today-action-list" :aria-label="__('Today\'s Actions')">
          <RouterLink v-if="canSeeArrivals" to="/arrivals"><span>{{ __("Reception & Check-in") }}</span><small>{{ __("Register the arrival and choose their bed") }}</small></RouterLink>
          <RouterLink v-if="canSeeBeds" to="/beds"><span>{{ __("Rooms & Beds") }}</span><small>{{ __("Room readiness and departure") }}</small></RouterLink>
          <RouterLink v-if="canSeeCustody" to="/custody"><span>{{ __("Custody Items") }}</span><small>{{ __("Issue and receive custody items") }}</small></RouterLink>
          <RouterLink v-if="canCreateMaintenance" to="/maintenance/new"><span>{{ __("Maintenance Request") }}</span><small>{{ __("Log a report for the building") }}</small></RouterLink>
        </nav>
      </section>
    </template>
  </section>
</template>
