<template>
  <div class="space-y-4">
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

    <Skeleton v-if="active.loading" :rows="3" />

    <ErrorState v-else-if="active.error" :message="t('errors.loadFailed')" @retry="active.reload()" />

    <EmptyState
      v-else-if="!active.data || !active.data.length"
      icon="route"
      :title="tab === 'today' ? t('trips.empty') : t('trips.recentEmpty')"
      :hint="tab === 'today' ? t('trips.emptyHint') : t('trips.recentEmptyHint')"
    />

    <div v-for="trip in active.data" v-else :key="trip.name" class="card card-pad">
      <router-link :to="'/route/' + encodeURIComponent(trip.name)" class="block" style="text-decoration: none; color: inherit">
        <div class="flex items-start justify-between gap-2">
          <div class="font-bold leading-tight"><bdi>{{ trip.route_plan || trip.name }}</bdi></div>
          <span class="pill pill-accent shrink-0">{{ te("tripStatus", trip.status) }}</span>
        </div>
        <div class="mt-2 flex items-center gap-2 text-sm text-soft">
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

      <!-- Execution actions (today only): start → complete, writing a Trip Start Log. -->
      <div v-if="tab === 'today'" class="mt-3 flex items-center gap-2">
        <span v-if="trip.trip_log_status === 'Completed'" class="pill pill-success">
          <Icon name="badge" :size="14" /> {{ t("trips.completed") }}
        </span>
        <template v-else-if="trip.started">
          <span class="pill pill-warning"><Icon name="route" :size="14" /> {{ t("trips.started") }}</span>
          <button class="btn btn-dark" style="width: auto; padding-inline: 16px" :disabled="busy === trip.name" @click="complete(trip)">
            {{ t("trips.complete") }}
          </button>
        </template>
        <button v-else class="btn btn-primary" style="width: auto; padding-inline: 16px" :disabled="busy === trip.name" @click="start(trip)">
          <Icon name="route" :size="16" /> {{ t("trips.start") }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t, te, fmtTime } = useI18n();

const tab = ref("today");

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

async function start(trip) {
  if (busy.value) return;
  busy.value = trip.name;
  try {
    await startTrip.submit({ dispatch_trip: trip.name });
    today.reload(); // server re-stamps started/trip_log_status on each card
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
