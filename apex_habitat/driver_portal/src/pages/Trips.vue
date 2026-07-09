<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-4">
    <!-- Large Wait Request Notification Banner -->
    <div
      v-if="currentWait"
      class="fixed inset-x-4 top-4 z-[999] rounded-xl bg-orange-600 text-white p-4 shadow-2xl flex items-center justify-between gap-3 border border-orange-500 animate-bounce"
    >
      <div class="flex items-center gap-3 min-w-0">
        <div class="h-10 w-10 rounded-full bg-white/20 flex items-center justify-center shrink-0 animate-pulse">
          <Icon name="alert" :size="20" class="text-white" />
        </div>
        <div class="min-w-0 text-right">
          <h4 class="font-bold text-sm md:text-base leading-snug">طلب انتظار!</h4>
          <p class="text-xs md:text-sm opacity-90 truncate"><bdi>{{ currentWait.employee }}</bdi> يطلب الانتظار</p>
        </div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <div class="bg-white text-orange-600 font-extrabold text-base md:text-lg px-3 py-1.5 rounded-lg">
          {{ currentWait.seconds }}ث
        </div>
        <button @click="currentWait = null" class="p-1 rounded-full hover:bg-white/10" aria-label="Dismiss">
          <Icon name="x" :size="16" />
        </button>
      </div>
    </div>

    <h2 class="section-title">{{ t("trips.title") }}</h2>
    <p class="-mt-2 text-sm text-soft">{{ t("trips.subtitle") }}</p>

    <!-- Today is the default view; Recent shows the last 30 days (loaded lazily). -->
    <div class="seg" role="tablist">
      <button
        class="seg-btn"
        :class="{ 'seg-on': tab === 'today' }"
        role="tab"
        :aria-selected="tab === 'today'"
        @click="tab = 'today'"
      >
        {{ t("trips.today") }}
      </button>
      <button
        class="seg-btn"
        :class="{ 'seg-on': tab === 'recent' }"
        role="tab"
        :aria-selected="tab === 'recent'"
        @click="showRecent"
      >
        {{ t("trips.recent") }}
      </button>
    </div>

    <!-- Daily Summary Tiles (today only, when data is loaded) -->
    <div v-if="tab === 'today' && today.data && today.data.length" class="grid gap-3 grid-cols-3">
      <div class="stat">
        <div class="stat-label">{{ t("trips.todayTrips") }}</div>
        <div class="stat-value">{{ todayTripCount }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">{{ t("trips.completedTrips") }}</div>
        <div class="stat-value text-success">{{ completedTripCount }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">{{ t("trips.totalBoarded") }}</div>
        <div class="stat-value">{{ totalBoardedCount }}</div>
      </div>
    </div>

    <Skeleton v-if="active.loading" :rows="3" />

    <ErrorState v-else-if="active.error" :message="t('errors.loadFailed')" @retry="active.reload()" />

    <EmptyState
      v-else-if="!active.data || !active.data.length"
      icon="route"
      :title="tab === 'today' ? t('trips.empty') : t('trips.recentEmpty')"
      :hint="tab === 'today' ? t('trips.emptyHint') : t('trips.recentEmptyHint')"
    />

    <div
      v-for="trip in active.data"
      v-else
      :key="trip.name"
      class="card card-pad"
      :class="trip === nextTrip ? 'sticky top-4 z-10 shadow-xl border-primary/40 ring-1 ring-primary/30 transform transition-transform scale-[1.01]' : ''"
    >
      <router-link :to="'/route/' + encodeURIComponent(trip.name)" class="block" style="text-decoration: none; color: inherit">
        <div class="flex items-start justify-between gap-2">
          <div class="font-bold leading-tight"><bdi>{{ trip.route_plan || trip.name }}</bdi></div>
          <span class="pill pill-accent shrink-0">{{ te("tripStatus", trip.status) }}</span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-sm text-soft">
          <Icon name="truck" :size="16" class="text-primary shrink-0" />
          <span><bdi>{{ trip.vehicle || "—" }}</bdi></span>
          <!-- Direction-neutral, labelled times: reads correctly in LTR and RTL with
               no bare arrow. -->
          <span v-if="trip.depart_time" class="text-muted">·</span>
          <span v-if="trip.depart_time">
            {{ t("home.depart") }} <bdi>{{ fmtTime(trip.depart_time) }}</bdi>
          </span>
          <span v-if="trip.return_time" class="text-muted">·</span>
          <span v-if="trip.return_time">
            {{ t("home.return") }} <bdi>{{ fmtTime(trip.return_time) }}</bdi>
          </span>
          <Icon name="route" :size="16" class="text-primary shrink-0 ms-auto" />
        </div>
        <!-- The recent view spans days, so each card names its trip date. -->
        <div v-if="tab === 'recent' && trip.trip_date" class="mt-1 flex items-center gap-2 text-xs text-muted">
          <Icon name="calendar" :size="14" class="text-primary shrink-0" />
          <span><bdi>{{ trip.trip_date }}</bdi></span>
        </div>
      </router-link>

      <!-- One-tap navigation to the trip's first stop (same deep-link as Route). -->
      <a
        v-if="trip.google_maps_url"
        :href="trip.google_maps_url"
        target="_blank"
        rel="noopener"
        class="text-primary text-sm inline-flex items-center gap-1 mt-2"
      >
        <Icon name="map-pin" :size="14" /> {{ t("route.openMap") }}
      </a>

      <!-- Boarded headcount (today only): Circular Progress Ring -->
      <div
        v-if="tab === 'today' && trip.expected_count"
        class="mt-3 flex items-center gap-3 bg-gray-50/50 p-2.5 rounded-xl border border-gray-100"
      >
        <div class="relative w-10 h-10 shrink-0">
          <svg class="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="16" fill="none" class="stroke-gray-200" stroke-width="3"></circle>
            <circle cx="18" cy="18" r="16" fill="none" class="stroke-primary transition-all duration-700 ease-out" stroke-width="3" stroke-dasharray="100.53" :stroke-dashoffset="100.53 - (((trip.boarded_count || 0) / trip.expected_count) * 100.53)" stroke-linecap="round"></circle>
          </svg>
          <div class="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gray-700" dir="ltr">
            {{ Math.round(((trip.boarded_count || 0) / trip.expected_count) * 100) }}%
          </div>
        </div>
        
        <div class="flex-1 min-w-0">
          <div class="text-sm font-bold text-gray-800">{{ t("trips.boardedOf", { n: trip.boarded_count || 0, m: trip.expected_count }) }}</div>
        </div>
      </div>

      <!-- Execution actions (today only): start → complete, writing a Trip Start Log. -->
      <div v-if="tab === 'today'" class="mt-3 flex flex-wrap items-center gap-2">
        <span v-if="trip.trip_log_status === 'Completed'" class="pill pill-success">
          <Icon name="badge" :size="14" /> {{ t("trips.completed") }}
        </span>
        <template v-else-if="trip.started">
          <span class="pill pill-warning"><Icon name="route" :size="14" /> {{ t("trips.started") }}</span>
          <!-- Inline Boarding Actions -->
          <template v-if="trip.expected_count">
            <button class="btn btn-primary" style="width: auto; padding-inline: 16px" @click="openManifest(trip)">
              <Icon name="user" :size="16" /> {{ t("manifest.title", "Boarding") }}
            </button>
          </template>
          
          <button class="btn btn-dark" style="width: auto; padding-inline: 16px" :disabled="busy === trip.name" @click="complete(trip)">
            {{ t("trips.complete") }}
          </button>
        </template>
        <button v-else class="btn btn-primary" style="width: auto; padding-inline: 16px" :disabled="busy === trip.name" @click="start(trip)">
          <Icon name="route" :size="16" /> {{ t("trips.start") }}
        </button>
      </div>
    </div>

    <!-- QR boarding scanner (mounts only while open), scoped to the tapped trip. -->
    <BoardingScanner v-if="scanTrip" @close="scanTrip = null" @boarded="onBoarded" />
    <!-- Manual-boarding fallback sheet, scoped to the tapped trip. -->
    <ManualBoarding v-if="manualTrip" :trip="manualTrip.name" @close="manualTrip = null" @boarded="onBoarded" />
    <!-- Boarding manifest / depart panel, scoped to the tapped started trip. -->
    <BoardingManifest v-if="manifestTrip" :trip="manifestTrip.name" @close="manifestTrip = null" @finalized="onFinalized" @open-scan="openScanner(manifestTrip); manifestTrip = null" @open-manual="openManual(manifestTrip); manifestTrip = null" />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import BoardingScanner from "../components/BoardingScanner.vue";
import ManualBoarding from "../components/ManualBoarding.vue";
import BoardingManifest from "../components/BoardingManifest.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import { connectDriverRealtime } from "../realtime.js";

const { t, te, fmtTime, dir } = useI18n();

const tab = ref("today");

const activeBoardingTrip = ref(null);
function toggleBoardingMenu(trip) {
  if (activeBoardingTrip.value === trip.name) {
    activeBoardingTrip.value = null;
  } else {
    activeBoardingTrip.value = trip.name;
  }
}

const currentWait = ref(null);
let waitTimer = null;

function showWaitNotification(payload) {
  if (waitTimer) clearInterval(waitTimer);
  currentWait.value = {
    employee: payload.employee || "موظف",
    seconds: payload.wait_window_seconds || 60,
  };
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
    gainNode.gain.setValueAtTime(0.5, audioContext.currentTime);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.3);
  } catch (e) {
    // ignore audio block
  }
  waitTimer = setInterval(() => {
    if (currentWait.value) {
      currentWait.value.seconds--;
      if (currentWait.value.seconds <= 0) {
        clearInterval(waitTimer);
        currentWait.value = null;
      }
    } else {
      clearInterval(waitTimer);
    }
  }, 1000);
}

function onBoardingEvent(event, payload) {
  if (event === "wait_request") {
    showWaitNotification(payload);
  }
}

// The trip whose boarding scanner is open (null = closed). A Valid scan reloads
// today's trips so the card's "N of M boarded" increments.
const scanTrip = ref(null);
function openScanner(trip) {
  scanTrip.value = trip;
}
// The trip whose manual-boarding sheet is open (null = closed).
const manualTrip = ref(null);
function openManual(trip) {
  manualTrip.value = trip;
}
// The trip whose boarding manifest / depart panel is open (null = closed).
const manifestTrip = ref(null);
function openManifest(trip) {
  manifestTrip.value = trip;
}
function onBoarded() {
  today.reload();
}
// Depart finalized the trip: refresh the card (its boarded/absent counts) and
// close the panel so the summary doesn't linger.
function onFinalized() {
  today.reload();
  manifestTrip.value = null;
}

const today = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trips_today",
  auto: true,
});
const recent = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trips_recent",
});

// Recent is fetched only the first time its tab is opened (then cached).
function showRecent() {
  tab.value = "recent";
  if (!recent.data && !recent.loading) recent.fetch();
}

const active = computed(() => (tab.value === "recent" ? recent : today));

// Daily summary tile computations (today tab only).
const todayTripCount = computed(() => (today.data || []).length);
const completedTripCount = computed(
  () => (today.data || []).filter((t) => t.trip_log_status === "Completed").length,
);
const totalBoardedCount = computed(
  () => (today.data || []).reduce((sum, t) => sum + (t.boarded_count || 0), 0),
);

// Identify the very next trip for sticky highlight
const nextTrip = computed(() => {
  if (tab.value !== "today" || !today.data) return null;
  return today.data.find(
    (t) => t.trip_log_status !== "Completed" && t.status !== "Completed" && t.status !== "Cancelled"
  ) || null;
});

// ── Realtime (socket push, ahead of a manual refresh) ──
// When a Dispatch Trip the driver can read changes (assignment / status / board),
// the server publishes `driver_trip_update`; refetch today's trips at once. Every
// failure is swallowed in realtime.js, so if the socket never connects the
// existing fetch / pull-to-refresh still carries the trips. Recent is left to its
// own lazy load (operational pushes are about today's active trips).
let stopRealtime = () => {};
function onTripUpdate() {
  today.reload();
}
onMounted(() => {
  stopRealtime = connectDriverRealtime(onTripUpdate, onBoardingEvent);
});
onUnmounted(() => {
  stopRealtime();
  stopPositionTracking();
  if (waitTimer) clearInterval(waitTimer);
});

// --- Trip execution: start → complete, writing a Trip Start Log. ---
// `busy` holds the trip name in flight so its buttons disable (single tap = single write).
const busy = ref(null);

const startTrip = createResource({
  url: "apex_habitat.salis.api.driver_portal.start_my_trip",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
const completeTrip = createResource({
  url: "apex_habitat.salis.api.driver_portal.complete_my_trip",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

// --- Live position push: while a started trip is in progress, periodically read
// the driver's GPS and push it so the worker's Masar Home shows a live ride ETA.
// Opt-in and graceful: if the browser has no geolocation or the driver denies the
// permission prompt, the push is simply skipped (the ride still runs; the worker
// just sees no live ETA). One tracker at a time — a new start supersedes the old.
const POSITION_PUSH_INTERVAL_MS = 30000; // 30s cadence — a glanceable, not live, ETA
const pushPosition = createResource({
  url: "apex_habitat.salis.api.driver_portal.push_driver_position",
  // Best-effort telemetry: a failed push must never toast/interrupt the driver.
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
    () => {}, // permission denied / unavailable — skip silently (opt-in)
    { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 }
  );
}
function startPositionTracking(tripName) {
  stopPositionTracking();
  if (!navigator.geolocation) return; // no geolocation support: nothing to do
  trackedTrip = tripName;
  pushOnce(); // immediate first fix, then on the interval
  positionTimer = setInterval(pushOnce, POSITION_PUSH_INTERVAL_MS);
}
function stopPositionTracking() {
  if (positionTimer) clearInterval(positionTimer);
  positionTimer = null;
  trackedTrip = null;
}
onUnmounted(stopPositionTracking);

async function start(trip) {
  if (busy.value) return;
  busy.value = trip.name;
  try {
    await startTrip.submit({ dispatch_trip: trip.name });
    today.reload(); // server re-stamps started/trip_log_status on each card
    startPositionTracking(trip.name); // begin live-position push for the ETA
  } finally {
    busy.value = null;
  }
}
async function complete(trip) {
  if (busy.value) return;
  busy.value = trip.name;
  try {
    await completeTrip.submit({ dispatch_trip: trip.name });
    today.reload();
    if (trackedTrip === trip.name) stopPositionTracking(); // trip done: stop pushing
  } finally {
    busy.value = null;
  }
}
</script>

<style scoped>
.seg {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border-radius: 999px;
  background: var(--c-surface-2, #f1f1f1);
  border: 1px solid var(--c-border, rgba(0, 0, 0, 0.08));
}
.seg-btn {
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--c-ink-soft, #555);
}
.seg-on {
  background: var(--c-primary, #2563eb);
  color: var(--c-primary-ink, #fff);
}
</style>
