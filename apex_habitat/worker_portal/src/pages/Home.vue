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

      <!-- Open requests stat -->
      <div class="grid gap-3 grid-cols-1">
        <div class="stat">
          <div class="stat-label">{{ t("home.openRequests") }}</div>
          <div class="stat-value">{{ home.data.open_request_count }}</div>
        </div>
      </div>

      <!-- My bed: building + room + bed, not just a bare code. Each code is
           <bdi>-wrapped so the Latin bed/room ids stay LTR inside the RTL card. -->
      <section v-if="bed" class="card card-pad space-y-2">
        <div class="flex items-center gap-2">
          <Icon name="home" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("home.bed") }}</span>
          <span class="font-extrabold ms-auto shrink-0"><bdi>{{ bed.bed_code || bed.name }}</bdi></span>
        </div>
        <div v-if="bedBuilding" class="flex items-center gap-2 text-sm">
          <Icon name="pin" :size="16" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("accommodation.building") }}</span>
          <span class="ms-auto font-semibold"><bdi>{{ bedBuilding }}</bdi></span>
        </div>
        <div v-if="bedRoom" class="flex items-center gap-2 text-sm">
          <Icon name="bed" :size="16" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("accommodation.room") }}</span>
          <span class="ms-auto font-semibold"><bdi>{{ bedRoom }}</bdi><span v-if="bed.floor != null" class="text-muted font-normal"> · {{ t("accommodation.floor") }} <bdi>{{ bed.floor }}</bdi></span></span>
        </div>
        <div v-if="bed.check_in_date" class="flex items-center gap-2 text-sm">
          <Icon name="clock" :size="16" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("accommodation.checkIn") }}</span>
          <span class="ms-auto font-semibold"><bdi>{{ formatDate(bed.check_in_date) }}</bdi></span>
        </div>
      </section>

      <!-- Documents to renew: only when there is at least one alert. -->
      <section v-if="alerts.length" class="card card-pad card-primary space-y-3">
        <div class="flex items-center gap-2">
          <Icon name="alert" :size="18" class="text-warning shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("home.alerts") }}</span>
        </div>
        <ul class="space-y-2">
          <li v-for="doc in alerts" :key="doc.type" class="flex flex-col gap-2">
            <div class="flex items-center gap-2 text-sm">
              <Icon name="doc" :size="16" class="text-primary shrink-0" />
              <span class="font-semibold">{{ t("profile." + doc.type) }}</span>
              <span class="pill ms-auto shrink-0" :class="alertPill(doc).cls">{{ alertPill(doc).text }}</span>
            </div>
            <!-- [T-324] One-tap "notify HR" — only for an Iqama at or inside 30
                 days. The server re-checks the window, so this is a UI affordance,
                 not the gate. -->
            <template v-if="canNotifyHr(doc)">
              <button
                v-if="!hrNotified"
                class="btn btn-primary"
                style="width: auto; align-self: flex-start; padding-inline: 18px"
                :disabled="notifyHr.loading"
                @click="sendNotifyHr"
              >
                {{ notifyHr.loading ? t("home.notifyHrSending") : t("home.notifyHr") }}
              </button>
              <p v-else class="status-ok flex items-center gap-2 text-sm" style="align-self: flex-start">
                <Icon name="check" :size="16" class="shrink-0" />
                {{ t("home.notifyHrDone") }}
              </p>
              <p v-if="notifyHrError" class="text-sm text-danger">{{ notifyHrError }}</p>
            </template>
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
import { formatDate, formatDateTime, formatTime } from "../datetime";
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

// The bed chip now reads as a real location: prefer the human building/room name,
// fall back to the id, and show nothing (clean omit) when neither exists.
const bedBuilding = computed(() => bed.value?.building_name || bed.value?.building || "");
const bedRoom = computed(() => bed.value?.room_number || bed.value?.room || "");

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

// [T-324] The action threshold (30d) is tighter than the alert lead (60d) the
// card uses, so only an Iqama at or inside 30 days offers the one-tap button.
// The server re-checks this same window before raising anything.
const IQAMA_NOTIFY_HR_LEAD_DAYS = 30;
function canNotifyHr(doc) {
  return (
    doc.type === "iqama" && doc.days_left != null && doc.days_left <= IQAMA_NOTIFY_HR_LEAD_DAYS
  );
}

const hrNotified = ref(false);
const notifyHrError = ref("");
const notifyHr = createResource({
  url: "apex_habitat.salis.api.masar.notify_hr_iqama_expiring",
  onSuccess: () => {
    hrNotified.value = true;
    notifyHrError.value = "";
  },
  onError: (e) => {
    notifyHrError.value = resourceErrorMessage(e, "home.notifyHrFailed");
  },
});

function sendNotifyHr() {
  notifyHrError.value = "";
  notifyHr.submit({ token: TOKEN });
}
</script>
