<template>
  <div class="space-y-5">
    <!-- [T-320] pull-to-refresh indicator (page scrolls with the window) -->
    <PullIndicator :distance="ptr.distance.value" :refreshing="ptr.refreshing.value" :threshold="ptr.THRESHOLD" />

    <h2 class="section-title">{{ t("transport.title") }}</h2>

    <template v-if="tr.loading">
      <Skeleton :lines="4" />
      <Skeleton :lines="3" />
    </template>

    <!-- Error: a revoked/disabled token (PermissionError) or a server failure
         must surface, not show as a benign "no upcoming transport" empty state. -->
    <div v-else-if="tr.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="tr.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="upcoming.length || past.length">
      <!-- Upcoming trips: the only ones Home's "next ride" can ever point at. -->
      <section v-for="trip in upcoming" :key="trip.transport_request" class="card card-pad space-y-3">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-extrabold leading-tight truncate">
              {{ trip.request_type ? tEnum("requestType", trip.request_type) : trip.transport_request }}
            </div>
            <div v-if="trip.pickup_point || trip.pickup_datetime" class="mt-0.5 text-sm text-muted">
              <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
              <span v-if="trip.depart_time || trip.pickup_datetime"> · <bdi>{{ trip.depart_time ? formatTime(trip.depart_time) : formatDateTime(trip.pickup_datetime) }}</bdi></span>
            </div>
          </div>
          <span v-if="trip.status" class="pill pill-accent shrink-0">{{ tEnum("transportStatus", trip.status) }}</span>
        </div>

        <!-- Vehicle + driver -->
        <div v-if="trip.vehicle || trip.driver" class="grid grid-cols-1 gap-3">
          <div v-if="trip.vehicle" class="flex items-center gap-2 text-sm">
            <Icon name="truck" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.vehicle") }}</span>
            <span class="ms-auto font-semibold">
              <bdi>{{ trip.vehicle.plate_number || trip.vehicle.name }}</bdi>
              <span v-if="trip.vehicle.vehicle_category" class="text-muted font-normal">· {{ trip.vehicle.vehicle_category }}</span>
            </span>
          </div>
          <div v-if="trip.driver" class="flex items-center gap-2 text-sm">
            <Icon name="user" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.driver") }}</span>
            <span class="ms-auto font-semibold">{{ trip.driver.full_name }}</span>
          </div>
          <div v-if="trip.driver && trip.driver.phone" class="grid grid-cols-2 gap-3">
            <a :href="'tel:' + trip.driver.phone" class="btn btn-primary" style="text-decoration: none">
              <Icon name="phone" :size="18" /> {{ t("common.call") }}
            </a>
            <a :href="waLink(trip.driver.phone)" target="_blank" rel="noopener" class="btn btn-accent" style="text-decoration: none">
              <Icon name="message" :size="18" /> {{ t("common.whatsapp") }}
            </a>
          </div>
        </div>

        <!-- Ordered route stops -->
        <div v-if="trip.stops && trip.stops.length">
          <div class="field-label">{{ t("transport.stops") }}</div>
          <ol class="space-y-2">
            <li v-for="(stop, i) in trip.stops" :key="i" class="flex items-start gap-3">
              <span class="avatar h-6 w-6 text-xs shrink-0"
                    style="background: var(--c-primary); color: var(--c-primary-ink); border-radius: var(--radius-sm)">
                {{ stop.sequence || i + 1 }}
              </span>
              <div class="min-w-0">
                <div class="font-semibold leading-tight">
                  {{ stop.stop_name || t("transport.stop") }}
                  <span v-if="stop.planned_time" class="text-muted font-normal">· <bdi>{{ formatTime(stop.planned_time) }}</bdi></span>
                </div>
                <div v-if="stop.pickup" class="text-sm text-muted">
                  {{ stop.pickup.building_name || stop.accommodation_building }}
                  <span v-if="stop.pickup.city">, {{ stop.pickup.city }}</span>
                </div>
                <div v-else-if="stop.location" class="text-sm text-muted">{{ stop.location }}</div>
              </div>
            </li>
          </ol>
        </div>

        <!-- No planned route yet: an explicit state so the trip card is never a bare/inert card. -->
        <div v-else class="text-sm text-muted">{{ t("transport.noRoutePlanned") }}</div>

        <!-- [T-323] "I'm at the pickup": one-tap worker boarding self-confirm. The
             server resolves the worker from the token and writes the boarding
             event onto this trip — the button is a UI affordance, not the gate. -->
        <div>
          <button
            v-if="!confirmedTrips[trip.transport_request]"
            class="btn btn-primary"
            style="width: auto; padding-inline: 18px"
            :disabled="boarding.loading && boardingFor === trip.transport_request"
            @click="confirmBoarding(trip)"
          >
            <Icon name="check" :size="18" />
            {{ boarding.loading && boardingFor === trip.transport_request ? t("transport.atPickupSending") : t("transport.atPickup") }}
          </button>
          <p v-else class="status-ok flex items-center gap-2 text-sm">
            <Icon name="check" :size="16" class="shrink-0" />
            {{ t("transport.atPickupDone") }}
          </p>
          <p v-if="boardingError && boardingFor === trip.transport_request" class="text-sm text-danger mt-1">{{ boardingError }}</p>
        </div>
      </section>

      <!-- No upcoming trip, but past ones exist: say so explicitly so the screen
           agrees with Home ("No upcoming ride") instead of looking broken. -->
      <div v-if="!upcoming.length" class="card card-pad text-center">
        <p class="text-sm text-muted">{{ t("transport.empty") }}</p>
        <p class="text-xs text-muted mt-1">{{ t("transport.emptyHint") }}</p>
      </div>

      <!-- Past trips: a compact, de-emphasised history so a departed trip is
           never mistaken for the next ride. Collapsed by default. -->
      <section v-if="past.length" class="card card-pad space-y-3">
        <button class="flex w-full items-center gap-2" @click="showPast = !showPast">
          <Icon name="clock" :size="18" class="text-muted shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("transport.past") }}</span>
          <span class="pill pill-neutral shrink-0">{{ past.length }}</span>
          <Icon name="chevron" :size="18" class="text-muted shrink-0 ms-auto" :style="showPast ? 'transform: rotate(90deg)' : ''" />
        </button>
        <ul v-if="showPast" class="space-y-2">
          <li v-for="trip in past" :key="trip.transport_request" class="flex items-start gap-2 text-sm">
            <Icon name="route" :size="16" class="text-muted shrink-0 mt-0.5 rtl-flip" />
            <div class="min-w-0">
              <div class="font-semibold leading-tight truncate">
                {{ trip.request_type ? tEnum("requestType", trip.request_type) : trip.transport_request }}
              </div>
              <div v-if="trip.pickup_point || trip.pickup_datetime" class="text-muted">
                <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
                <span v-if="trip.depart_time || trip.pickup_datetime"> · <bdi>{{ trip.depart_time ? formatTime(trip.depart_time) : formatDateTime(trip.pickup_datetime) }}</bdi></span>
              </div>
            </div>
          </li>
        </ul>
      </section>

      <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
        <Icon name="plus" :size="18" /> {{ t("transport.reportIssue") }}
      </router-link>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("transport.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("transport.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import PullIndicator from "../components/PullIndicator.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatTime, formatDateTime } from "../datetime";
import { TOKEN } from "../token";
import { waLink } from "../phone";
import { usePullToRefresh } from "../usePullToRefresh";

const { t, tEnum } = useI18n();

const tr = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_transport",
  params: { token: TOKEN },
  auto: true,
});

// [T-320] pull down at the top to refresh upcoming trips. reload() returns the
// fetch promise, so the spinner keeps spinning until the data lands.
const ptr = usePullToRefresh(() => tr.reload());

const errorMessage = computed(() => resourceErrorMessage(tr.error));

// [T-537] upcoming vs past — the backend splits on the same now_datetime() pivot
// Home uses, so the trip Home shows as "next ride" is exactly upcoming[0].
// (Older payloads only had a flat `trips`; fall back to it as the upcoming list.)
const upcoming = computed(() => tr.data?.upcoming || tr.data?.trips || []);
const past = computed(() => tr.data?.past || []);
const showPast = ref(false);

// [T-323] worker boarding self-confirm. The server resolves the worker from the
// token and writes the boarding event; this UI just records which trips the
// worker has already confirmed so the card flips to a done state. Keyed by
// transport_request so each card tracks its own state.
const confirmedTrips = reactive({});
const boardingFor = ref(null);
const boardingError = ref("");
const boarding = createResource({
  url: "apex_habitat.salis.api.masar.confirm_boarding",
  onSuccess: () => {
    confirmedTrips[boardingFor.value] = true;
    boardingError.value = "";
  },
  onError: (e) => {
    boardingError.value = resourceErrorMessage(e, "transport.atPickupFailed");
  },
});

function confirmBoarding(trip) {
  boardingFor.value = trip.transport_request;
  boardingError.value = "";
  boarding.submit({ token: TOKEN, transport_request: trip.transport_request });
}
</script>
