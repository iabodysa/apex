<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import { statusLabel } from "../../core/displayLabels.js";
import { createLeafletAdapter } from "./leafletAdapter.js";
import { createTransportMapState, positionStateLabel, selectedMapRows } from "./transportMapState.js";
import "./styles.css";
import PortalErrorState from "../../components/PortalErrorState.vue";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import { __ } from "../../core/i18n.js";

const positions = createResource({
  url: "apex.salis.api.route_supervisor.get_active_driver_positions",
  method: "GET",
  auto: false,
});
const mapRoot = ref(null);
const mapState = createTransportMapState();
const mapAdapter = createLeafletAdapter();
const { phase: state, error, positions: loaded, project, status, projects, statuses, visible } = mapState;
const selectedTrip = ref("");
const selected = computed(() => visible.value.find((item) => item.dispatch_trip === selectedTrip.value) || visible.value[0] || null);

async function draw() {
  if (!mapRoot.value || state.value !== "ready") return;
  try {
    await mapAdapter.draw(mapRoot.value, selectedMapRows(visible.value, selectedTrip.value));
  } catch (reason) {
    mapState.fail(reason);
  }
}

async function load() {
  const committed = await mapState.load(() => positions.fetch());
  if (!committed) return;
  if (!visible.value.some((item) => item.dispatch_trip === selectedTrip.value)) {
    selectedTrip.value = visible.value[0]?.dispatch_trip || "";
  }
  await nextTick();
  await draw();
}

async function applyFilters() {
  if (!visible.value.some((item) => item.dispatch_trip === selectedTrip.value)) {
    selectedTrip.value = visible.value[0]?.dispatch_trip || "";
  }
  await nextTick();
  await draw();
}

async function updateProject(value) {
  project.value = value || "";
  await applyFilters();
}

async function updateStatus(value) {
  status.value = value || "";
  await applyFilters();
}

async function selectTrip(name) {
  selectedTrip.value = name;
  await nextTick();
  await draw();
}

onMounted(load);
onBeforeUnmount(() => {
  mapState.cancel();
  mapAdapter.destroy();
});
</script>

<template>
  <section class="feature-page transport-map-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div>
        <p class="feature-page__eyebrow">{{ __("Transport Operations") }}</p>
        <h2>{{ __("Live Map") }}</h2>
        <p>{{ __("Driver locations and the routes of trips assigned to you.") }}</p>
      </div>
      <Button variant="outline" icon-left="lucide-refresh-cw" :loading="state === 'loading'" :disabled="state === 'loading'" @click="load">{{ __("Refresh") }}</Button>
    </header>
    <!-- `load` serves both the first paint (`onMounted`) and the refresh button, so the pending
         phase means two different things. With nothing on screen yet it is a content load and
         gets the skeleton the contract requires. With trips already drawn it is a refresh, and
         replacing the map with a placeholder would take away what the supervisor is reading —
         the Button's own LoadingIndicator (node_modules/frappe-ui/src/components/Button/Button.vue:23)
         and this section's `aria-busy` already report it. -->
    <PortalSkeleton
      v-if="state === 'loading' && !loaded.length"
      :rows="4"
      :label="__('Loading Vehicle Movement')"
    />
    <PortalErrorState v-else-if="state === 'denied'" :title="__('Could not open the map')" :message="__('You do not have permission for these trips.')" @retry="load" />
    <PortalErrorState v-else-if="state === 'error'" :title="__('Could not load the map')" :message="error" @retry="load" />
    <div v-else-if="state === 'empty'" class="feature-state">{{ __("No active trips right now.") }}</div>
    <template v-else>
      <div class="transport-map-filters">
        <FormControl :model-value="project" type="select" :label="__('Project')" :options="[{ label: __('All Projects'), value: '' }, ...projects]" @update:model-value="updateProject" />
        <FormControl :model-value="status" type="select" :label="__('Status')" :options="[{ label: __('All Statuses'), value: '' }, ...statuses.map((value) => ({ label: statusLabel(value), value }))]" @update:model-value="updateStatus" />
      </div>
      <ul class="transport-map-legend" :aria-label="__('Map Legend')">
        <li data-kind="route">{{ __("Trip Route") }}</li>
        <li data-kind="live">{{ __("Live Position") }}</li>
        <li data-kind="stale">{{ __("Delayed Position") }}</li>
        <li data-kind="unknown">{{ __("Freshness Unknown") }}</li>
        <li data-kind="stop">{{ __("Stop Point") }}</li>
      </ul>
      <div ref="mapRoot" class="transport-map" :aria-label="__('Vehicle Movement Map')" />
      <article v-if="selected" class="transport-map-selection">
        <div class="record-identity">
          <span>{{ __("Selected Trip") }}</span>
          <strong dir="auto">{{ selected.route_name || __("Operational Trip") }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ selected.dispatch_trip }}</bdi>
        </div>
        <dl>
          <div><dt>{{ __("driver") }}</dt><dd>{{ selected.driver_name || __("Not Assigned") }}</dd></div>
          <div><dt>{{ __("vehicle") }}</dt><dd><bdi dir="auto" translate="no">{{ selected.plate || __("Unassigned Vehicle") }}</bdi></dd></div>
          <div><dt>{{ __("Project") }}</dt><dd dir="auto">{{ selected.project_label || selected.project || __("Unspecified") }}</dd></div>
        </dl>
        <RouterLink class="transport-map-selection__action" :to="`/trips/${selected.dispatch_trip}`">{{ __("Open Trip Operation") }}</RouterLink>
      </article>
      <div class="transport-map-list" aria-live="polite">
        <button v-for="item in visible" :key="item.dispatch_trip" type="button" class="feature-card transport-map-card" :aria-pressed="item.dispatch_trip === selected?.dispatch_trip" @click="selectTrip(item.dispatch_trip)">
          <div>
            <strong dir="auto">{{ item.route_name || item.route_plan }}</strong>
            <span><bdi dir="auto">{{ item.driver_name || __("Driver not specified") }}</bdi> · <bdi dir="auto" translate="no">{{ item.plate || __("Vehicle not specified") }}</bdi></span>
          </div>
          <span
            class="transport-map-status"
            :data-state="item.position_state"
          >{{ positionStateLabel(item.position_state) }}</span>
        </button>
      </div>
    </template>
  </section>
</template>
