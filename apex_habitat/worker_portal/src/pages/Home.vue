<template>
  <div class="space-y-5">
    <!-- [T-320] pull-to-refresh indicator (page scrolls with the window) -->
    <PullIndicator :distance="ptr.distance.value" :refreshing="ptr.refreshing.value" :threshold="ptr.THRESHOLD" />

    <h2 class="section-title">{{ t("home.title") }}</h2>

    <template v-if="home.loading">
      <Skeleton :lines="2" />
      <Skeleton variant="stats" :lines="2" />
    </template>

    <!-- Error: a revoked/disabled token (PermissionError) or a server failure
         must surface, not show as a benign empty state. -->
    <div v-else-if="home.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="home.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="home.data">
      <!-- Next ride -->
      <section class="card card-pad space-y-3" :class="{ 'card-primary': !alerts.length && ride }">
        <div class="flex items-center gap-2">
          <Icon name="route" :size="18" class="text-primary shrink-0 rtl-flip" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("home.nextRide") }}</span>
          <span v-if="ride && ride.status" class="pill pill-accent ms-auto shrink-0">{{ tEnum("transportStatus", ride.status) }}</span>
        </div>

        <template v-if="ride">
          <div class="font-extrabold leading-tight truncate">
            {{ ride.request_type ? tEnum("requestType", ride.request_type) : ride.transport_request }}
          </div>
          <div v-if="ride.pickup_point" class="flex items-center gap-2 text-sm">
            <Icon name="pin" :size="16" class="text-primary shrink-0" />
            <span class="font-semibold">{{ ride.pickup_point }}</span>
          </div>
          <div v-if="rideWhen" class="flex items-center gap-2 text-sm">
            <Icon name="clock" :size="16" class="text-primary shrink-0" />
            <span class="font-semibold"><bdi>{{ rideWhen }}</bdi></span>
            <span v-if="relativeHint" class="pill pill-neutral ms-auto shrink-0">{{ relativeHint }}</span>
          </div>
        </template>

        <p v-else class="text-sm text-muted">{{ t("home.noRide") }}</p>
      </section>

      <!-- Stat row: open requests + bed chip -->
      <div class="grid gap-3" :class="bed ? 'grid-cols-2' : 'grid-cols-1'">
        <div class="stat">
          <div class="stat-label">{{ t("home.openRequests") }}</div>
          <div class="stat-value">{{ home.data.open_request_count }}</div>
        </div>
        <div v-if="bed" class="stat">
          <div class="stat-label">{{ t("home.bed") }}</div>
          <div class="stat-value"><bdi>{{ bed.bed_code || bed.name }}</bdi></div>
        </div>
      </div>

      <!-- Documents to renew: only when there is at least one alert. -->
      <section v-if="alerts.length" class="card card-pad card-primary space-y-3">
        <div class="flex items-center gap-2">
          <Icon name="alert" :size="18" class="text-warning shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("home.alerts") }}</span>
        </div>
        <ul class="space-y-2">
          <li v-for="doc in alerts" :key="doc.type" class="flex items-center gap-2 text-sm">
            <Icon name="doc" :size="16" class="text-primary shrink-0" />
            <span class="font-semibold">{{ t("profile." + doc.type) }}</span>
            <span class="pill ms-auto shrink-0" :class="alertPill(doc).cls">{{ alertPill(doc).text }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import PullIndicator from "../components/PullIndicator.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDateTime, formatTime } from "../datetime";
import { TOKEN } from "../token";
import { usePullToRefresh } from "../usePullToRefresh";

const { t, tEnum } = useI18n();

// One call: the backend folds profile alerts, next ride, bed and the open
// request count into a single token-scoped "today" payload. [#hometdy]
const home = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_home",
  params: { token: TOKEN },
  auto: true,
});

// [T-320] pull down at the top to refresh today's payload. reload() returns the
// fetch promise, so the spinner keeps spinning until the data lands.
const ptr = usePullToRefresh(() => home.reload());

const errorMessage = computed(() => resourceErrorMessage(home.error));

const ride = computed(() => home.data?.next_ride || null);
const bed = computed(() => home.data?.bed || null);
const alerts = computed(() => home.data?.profile_alerts || []);

// A ticking "now" so the relative hint stays honest; cleared on unmount.
const now = ref(Date.now());
const timer = setInterval(() => (now.value = Date.now()), 60000);
onUnmounted(() => clearInterval(timer));

// The ride's moment as a backend string: a depart clock-time falls back to the
// full pickup datetime. Localized + <bdi>-wrapped in the template.
const rideAt = computed(() => ride.value?.pickup_datetime || null);
const rideWhen = computed(() => {
  const r = ride.value;
  if (!r) return "";
  if (r.depart_time) return formatTime(r.depart_time);
  return r.pickup_datetime ? formatDateTime(r.pickup_datetime) : "";
});

// "Now" / "in Xm" / "in Xh Ym" for a pickup later TODAY; "Today" if it's today
// but the time isn't parseable; "" for a past pickup or a different day (the
// absolute datetime still shows either way).
const relativeHint = computed(() => {
  const s = rideAt.value;
  if (!s) return "";
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!m) return "";
  const today = new Date();
  const sameDay =
    today.getFullYear() === +m[1] && today.getMonth() === +m[2] - 1 && today.getDate() === +m[3];
  if (!sameDay) return "";
  if (m[4] == null) return t("home.today");
  const at = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTime();
  const diffMin = Math.round((at - now.value) / 60000);
  if (diffMin < 0) return "";
  if (diffMin === 0) return t("home.now");
  if (diffMin < 60) return t("home.inM", { m: diffMin });
  return t("home.inHm", { h: Math.floor(diffMin / 60), m: diffMin % 60 });
});

function alertPill(doc) {
  const d = doc.days_left;
  if (d != null && d < 0) return { cls: "pill-danger", text: t("home.alertExpired") };
  return { cls: "pill-warning", text: t("home.alertDaysLeft", { n: d }) };
}
</script>
