<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <TripsSkeleton v-if="loading" :label="t('trips.loadingLabel')" />

  <LoadError
    v-else-if="active.error"
    :title="t('errors.tripsFailed')"
    :detail="loadErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="active.reload()"
  />

  <template v-else>
    <div class="hz-split">
      <div class="hz-split-list">
        <WaitRequestAlert v-if="wait" :request="wait" @dismiss="wait = null" />

        <TabButtons class="trip-tabs" v-model="tab" :dir="dir" :buttons="tabButtons" />

        <TripTotals v-if="live && rows.length" :trips="rows" />

        <EmptyState v-if="!rows.length" :title="emptyTitle" :hint="emptyHint">
          <template #icon><Icon name="route" :size="22" /></template>
          <template #action>
            <Button
              class="row-btn"
              variant="outline"
              :label="live ? t('trips.recent') : t('trips.today')"
              @click="tab = live ? 'recent' : 'today'"
            />
          </template>
        </EmptyState>

        <Panel v-else :title="t('trips.list')">
          <template #status>
            <Badge class="tone-badge" theme="gray" variant="subtle" size="lg" :label="n(rows.length)" />
          </template>
          <TripRow
            v-for="trip in rows"
            :key="trip.name"
            :trip="trip"
            :open="selected === trip.name"
            :show-boarding="live && !!trip.expected_count"
            @open="openTrip(trip.name)"
          />
        </Panel>
      </div>

      <aside v-if="desktop" class="hz-split-detail">
        <TripDetail
          v-if="selectedTrip"
          :trip="selectedTrip"
          :live="live"
          :busy="busy === selectedTrip.name"
          @scan="scanTrip = selectedTrip"
          @manual="manualTrip = selectedTrip"
          @complete="complete(selectedTrip)"
        />
        <div v-else class="pane pane-idle">
          <EmptyState :title="t('trips.pickTitle')" :hint="t('trips.pickHint')">
            <template #icon><Icon name="route" :size="22" /></template>
          </EmptyState>
        </div>
      </aside>
    </div>

    <div class="hz-dock" data-dock>
      <Button
        class="dock-btn"
        variant="solid"
        theme="green"
        size="2xl"
        :disabled="!step.trip"
        :loading="!!step.trip && busy === step.trip.name"
        :loading-text="t('trips.working')"
        :label="t('trips.step.' + step.key)"
        @click="runStep"
      >
        <template #prefix><Icon :name="STEP_ICONS[step.key]" :size="20" /></template>
      </Button>
      <p class="hz-dock-reason">{{ stepHint }}</p>
    </div>

    <Dialog
      v-if="!desktop"
      :modelValue="!!selectedTrip"
      :options="{ title: t('trips.detailTitle'), size: 'lg' }"
      @update:modelValue="(open) => !open && closeTrip()"
    >
      <template #body-content>
        <TripDetail
          v-if="selectedTrip"
          :trip="selectedTrip"
          :live="live"
          :busy="busy === selectedTrip.name"
          :framed="false"
          @scan="openOverlay('scan')"
          @manual="openOverlay('manual')"
          @complete="complete(selectedTrip)"
        />
      </template>
      <template #actions>
        <Button class="dock-btn" size="2xl" variant="outline" :label="t('common.done')" @click="closeTrip" />
      </template>
    </Dialog>

    <BoardingScanner v-if="scanTrip" @close="scanTrip = null" @boarded="onBoarded" />
    <ManualBoarding
      v-if="manualTrip"
      :trip="manualTrip.name"
      @close="manualTrip = null"
      @boarded="onBoarded"
    />
    <BoardingManifest
      v-if="manifestTrip"
      :trip="manifestTrip.name"
      @close="manifestTrip = null"
      @finalized="onFinalized"
      @open-scan="handoff('scan')"
      @open-manual="handoff('manual')"
    />
  </template>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Badge, Button, Dialog, TabButtons, createResource } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "@shared/components/Panel.vue";
import Icon from "../components/Icon.vue";
import LoadError from "@shared/components/LoadError.vue";
import TripsSkeleton from "../components/TripsSkeleton.vue";
import TripRow from "../components/TripRow.vue";
import TripDetail from "../components/TripDetail.vue";
import TripTotals from "../components/TripTotals.vue";
import WaitRequestAlert from "../components/WaitRequestAlert.vue";
import BoardingScanner from "../components/BoardingScanner.vue";
import ManualBoarding from "../components/ManualBoarding.vue";
import BoardingManifest from "../components/BoardingManifest.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { useDesktop } from "@shared/useBreakpoint.js";
import { pushToast } from "../toast";
import { useDriverRealtime } from "../realtime.js";
import { STEP_ICONS, dockStep } from "../trips";

const { t, n, dir } = useI18n();
const route = useRoute();
const router = useRouter();
const desktop = useDesktop();

const today = createResource({
  url: "apex.salis.api.driver_portal.my_trips_today",
  auto: true,
});
const recent = createResource({
  url: "apex.salis.api.driver_portal.my_trips_recent",
});

const tab = computed({
  get: () => (route.query.tab === "recent" ? "recent" : "today"),
  set: (value) => {
    const query = { ...route.query };
    delete query.trip;
    if (value === "recent") query.tab = "recent";
    else delete query.tab;
    router.replace({ path: route.path, query });
  },
});

watch(
  tab,
  (value) => {
    if (value === "recent" && !recent.data && !recent.loading) recent.fetch();
  },
  { immediate: true },
);

const live = computed(() => tab.value === "today");
const active = computed(() => (live.value ? today : recent));
const rows = computed(() => active.value.data || []);
const loading = computed(() => active.value.loading && !active.value.data);
const loadErrorMessage = computed(() =>
  resourceErrorMessage(active.value.error, "errors.tripsFailed"),
);

const tabButtons = computed(() => [
  { label: t("trips.today"), value: "today" },
  { label: t("trips.recent"), value: "recent" },
]);

const emptyTitle = computed(() => (live.value ? t("trips.empty") : t("trips.recentEmpty")));
const emptyHint = computed(() =>
  live.value ? t("trips.emptyHint") : t("trips.recentEmptyHint"),
);

const selected = computed(() => route.query.trip || "");
const selectedTrip = computed(() => rows.value.find((r) => r.name === selected.value) || null);

function openTrip(name) {
  router.push({ path: route.path, query: { ...route.query, trip: name } });
}
function closeTrip() {
  const query = { ...route.query };
  delete query.trip;
  router.push({ path: route.path, query });
}

const step = computed(() => dockStep(rows.value, selectedTrip.value, live.value));
const stepHint = computed(() => {
  if (!step.value.trip) return t("trips.stepHint." + step.value.key);
  return t("trips.stepHint." + step.value.key, {
    name: step.value.trip.route_plan || step.value.trip.name,
  });
});

const scanTrip = ref(null);
const manualTrip = ref(null);
const manifestTrip = ref(null);

function openOverlay(kind) {
  const trip = selectedTrip.value;
  closeTrip();
  if (kind === "scan") scanTrip.value = trip;
  else manualTrip.value = trip;
}
function handoff(kind) {
  const trip = manifestTrip.value;
  manifestTrip.value = null;
  if (kind === "scan") scanTrip.value = trip;
  else manualTrip.value = trip;
}
function onBoarded() {
  today.reload();
}
function onFinalized() {
  today.reload();
  manifestTrip.value = null;
}

const busy = ref(null);

const startTrip = createResource({
  url: "apex.salis.api.driver_portal.start_my_trip",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
const completeTrip = createResource({
  url: "apex.salis.api.driver_portal.complete_my_trip",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

function runStep() {
  const trip = step.value.trip;
  if (!trip) return;
  if (step.value.key === "start") return start(trip);
  if (step.value.key === "board") {
    manifestTrip.value = trip;
    return;
  }
  return complete(trip);
}

async function start(trip) {
  if (busy.value) return;
  busy.value = trip.name;
  try {
    await startTrip.submit({ dispatch_trip: trip.name });
    if (!startTrip.error) pushToast(t("trips.startedToast"), "ok");
    today.reload();
    startPositionTracking(trip.name);
  } finally {
    busy.value = null;
  }
}

async function complete(trip) {
  if (busy.value) return;
  busy.value = trip.name;
  try {
    await completeTrip.submit({ dispatch_trip: trip.name });
    if (!completeTrip.error) pushToast(t("trips.completedToast"), "ok");
    today.reload();
    if (trackedTrip === trip.name) stopPositionTracking();
  } finally {
    busy.value = null;
  }
}

const wait = ref(null);

/* A wait request names the bus it came from. Raising it without that name put a
   worker from one trip in front of a driver who was running another. */
function onPortalEvent(event, payload) {
  if (event === "driver_trip_update") {
    today.reload();
    return;
  }
  if (event !== "wait_request") return;
  const trip = payload.dispatch_trip || "";
  const row = trip ? rows.value.find((r) => r.name === trip) : null;
  if (trip && !row) return;
  wait.value = {
    employee: payload.employee || t("trips.defaultWorker"),
    seconds: payload.wait_window_seconds || 60,
    trip: row ? row.route_plan || row.name : "",
  };
}

useDriverRealtime(onPortalEvent);

onUnmounted(stopPositionTracking);

const POSITION_PUSH_INTERVAL_MS = 30000;
const pushPosition = createResource({
  url: "apex.salis.api.driver_portal.push_driver_position",
  onError: () => {},
});
let positionTimer = null;
let trackedTrip = null;

function pushOnce() {
  if (!trackedTrip || !navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      if (!trackedTrip) return;
      pushPosition.submit({
        dispatch_trip: trackedTrip,
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
      });
    },
    () => {},
    { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 },
  );
}
function startPositionTracking(tripName) {
  stopPositionTracking();
  if (!navigator.geolocation) return;
  trackedTrip = tripName;
  pushOnce();
  positionTimer = setInterval(pushOnce, POSITION_PUSH_INTERVAL_MS);
}
function stopPositionTracking() {
  if (positionTimer) clearInterval(positionTimer);
  positionTimer = null;
  trackedTrip = null;
}
</script>
