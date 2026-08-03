<!-- Copyright (c) 2026, AFMCO and contributors -->
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

          <!-- Live ETA row (Option A): shown ALONGSIDE the scheduled-time row
               above, never replacing it. `eta_minutes` is computed server-side
               from the driver's live GPS (compute_ride_eta_minutes in
               salis/api/masar.py) and is null until a position exists — then this
               slot falls back to the truthful en-route state, never a fabricated
               ETA (0 = driver at the pickup, a real value). -->
          <div v-if="rideEta !== null" class="flex items-center gap-2 text-sm">
            <Icon name="route" :size="16" class="text-primary shrink-0 rtl-flip" />
            <span class="font-semibold">{{ t("home.etaArriving", { eta: rideEta }) }}</span>
          </div>
          <div v-else-if="rideEnRoute" class="flex items-center gap-2 text-sm">
            <span class="eta-dot" aria-hidden="true"></span>
            <span class="font-semibold text-primary">{{ t("home.enRoute") }}</span>
          </div>
        </template>

        <p v-else class="text-sm text-muted">{{ t("home.noRide") }}</p>
      </section>

      <!-- 3-up glance tiles: next ride · open requests · days to Iqama.
           Each value is a compact glance; "—" when the datum is absent. -->
      <div class="grid gap-3 grid-cols-3">
        <div class="stat">
          <div class="stat-label">{{ t("home.tileNextRide") }}</div>
          <div class="stat-value truncate"><bdi>{{ nextRideTile }}</bdi></div>
        </div>
        <div class="stat">
          <div class="stat-label">{{ t("home.openRequests") }}</div>
          <div class="stat-value">{{ home.data.open_request_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">{{ t("home.tileIqama") }}</div>
          <div class="stat-value truncate" :class="iqamaTile.cls"><bdi>{{ iqamaTile.text }}</bdi></div>
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

    <!-- My Contacts: building in-charge, today's driver, housing office.
         Its own resource, so it renders even if the "today" payload is empty;
         shown only once at least one contact resolves. -->
    <!-- A first-load failure used to leave this card unrendered — visually identical
         to "no contacts are configured", hiding the numbers a worker calls for help. -->
    <section v-if="contacts.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("contacts.title") }}</p>
      <p class="text-sm text-muted">{{ contactsErrorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="contacts.reload()">
        {{ t("common.retry") }}
      </button>
    </section>

    <section v-else-if="contacts.data && hasContacts" class="card card-pad space-y-4">
      <div class="flex items-center gap-2">
        <Icon name="phone" :size="18" class="text-primary shrink-0" />
        <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("contacts.title") }}</span>
      </div>

      <ContactPerson v-if="buildingInCharge" :label="t('contacts.buildingInCharge')" :person="buildingInCharge" />
      <ContactPerson v-if="todayDriver" :label="t('contacts.todayDriver')" :person="todayDriver" />

      <div v-if="housingOffice" class="space-y-2">
        <div class="flex items-center gap-2 text-sm">
          <Icon name="building" :size="16" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("contacts.housingOffice") }}</span>
          <span class="ms-auto font-semibold"><bdi>{{ housingOffice }}</bdi></span>
        </div>
        <a :href="'tel:' + housingOffice" class="btn btn-primary" style="text-decoration: none">
          <Icon name="phone" :size="18" /> {{ t("common.call") }}
        </a>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, h, onUnmounted, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import PullIndicator from "../components/PullIndicator.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDate, formatDateTime, formatTime } from "../utils/datetime";
import { TOKEN } from "../utils/token";
import { waLink } from "../utils/phone";
import { usePullToRefresh } from "../composables/usePullToRefresh";

const { t, tEnum } = useI18n();

// One call: the backend folds profile alerts, next ride, bed and the open
// request count into a single token-scoped "today" payload. [#hometdy]
const home = createResource({
  url: "apex.salis.api.masar.get_worker_home",
  params: { token: TOKEN },
  auto: true,
  // Failure is owned here (and opted out of frappe-ui's global fallback handler);
  // frappe-ui rethrows regardless, so the template is what renders home.error.
  onError: () => {},
});

// The three home contacts (building in-charge, today's driver, housing office)
// are a separate token-scoped call so they refresh with the page.
const contacts = createResource({
  url: "apex.salis.api.masar.get_worker_contacts",
  params: { token: TOKEN },
  auto: true,
  // Failure is owned here (and opted out of frappe-ui's global fallback handler);
  // frappe-ui rethrows regardless, so the template is what renders contacts.error.
  onError: () => {},
});
const contactsErrorMessage = computed(() => resourceErrorMessage(contacts.error));
const buildingInCharge = computed(() => contacts.data?.building_in_charge || null);
// The driver carries full_name; normalize to the {name, phone} shape ContactPerson reads.
const todayDriver = computed(() => {
  const d = contacts.data?.today_driver;
  return d ? { name: d.full_name, phone: d.phone } : null;
});
const housingOffice = computed(() => contacts.data?.housing_office_number || "");
const hasContacts = computed(
  () => !!(buildingInCharge.value || todayDriver.value || housingOffice.value)
);

// [T-320] pull down at the top to refresh today's payload. reload() returns the
// fetch promise, so the spinner keeps spinning until the data lands; the contacts
// card refreshes alongside it.
const ptr = usePullToRefresh(() => Promise.all([home.reload(), contacts.reload()]));

const errorMessage = computed(() => resourceErrorMessage(home.error));

const ride = computed(() => home.data?.next_ride || null);
const bed = computed(() => home.data?.bed || null);

// Live ride ETA (T-331) — the server now computes it from the driver's live GPS
// position (pushed by the driver app while the trip is dispatched) to the worker's
// own pickup building; next_ride carries it as `eta_minutes`. Null until a position
// exists, so the card falls back to the truthful en-route state and never shows a
// fabricated ETA. 0 is a real value (driver at the pickup), so keep it.
const rideEta = computed(() => {
  const m = ride.value?.eta_minutes;
  return m === null || m === undefined ? null : m;
});

// The RIDE's own status, not the request's: "Dispatched" is a Dispatch Trip state
// meaning the driver has left, while the request beside it is still "Scheduled".
// Keyed on the raw stored English value; tEnum localizes the badge separately.
const rideEnRoute = computed(() => ride.value?.trip_status === "Dispatched");
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

// glance-tile values. Next-ride tile prefers the live relative hint
// ("in 2h 5m" / "Now" / "Today"); for a ride on another day (no hint) it shows
// the absolute moment, and "—" when there is no upcoming ride.
const nextRideTile = computed(() => {
  if (!ride.value) return t("common.none");
  return relativeHint.value || rideWhen.value || t("common.none");
});

// Days-to-Iqama tile, colour-keyed by urgency: danger when expired, warning
// within the 30-day action window, plain otherwise; "—" when no expiry on file.
const iqamaTile = computed(() => {
  const d = home.data?.iqama_days_left;
  if (d == null) return { cls: "", text: t("common.none") };
  if (d < 0) return { cls: "text-danger", text: t("home.expiredShort") };
  return {
    cls: d <= IQAMA_NOTIFY_HR_LEAD_DAYS ? "text-warning" : "",
    text: t("home.daysShort", { n: d }),
  };
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
  url: "apex.salis.api.masar.notify_hr_iqama_expiring",
  // The server re-reads the expiry and raises nothing outside its own window, answering
  // {"notified": false} — a 200 that means NOBODY was told. Confirming on the bare 200
  // told the worker HR had been informed. Reload the card too: the only way to reach
  // this is a days_left the page has been holding since before HR changed it.
  onSuccess: (data) => {
    hrNotified.value = !!(data && data.notified);
    notifyHrError.value = hrNotified.value ? "" : t("home.notifyHrFailed");
    if (!hrNotified.value) home.reload();
  },
  onError: (e) => {
    notifyHrError.value = resourceErrorMessage(e, "home.notifyHrFailed");
  },
});

function sendNotifyHr() {
  notifyHrError.value = "";
  notifyHr.submit({ token: TOKEN });
}

// One contact row (in-charge / driver): role label, name + phone, and
// tel/WhatsApp actions when a number is on file. Mirrors the Accommodation
// in-charge block so the two screens read the same. <bdi> isolates the LTR phone.
const ContactPerson = (cprops) => {
  const p = cprops.person;
  const phone = p.phone;
  return h("div", { class: "space-y-2" }, [
    h("div", { class: "flex items-center gap-3" }, [
      h(
        "span",
        { class: "avatar h-10 w-10", style: "background: var(--c-mint); color: var(--c-ink)" },
        h(Icon, { name: "user", size: 18 })
      ),
      h("div", { class: "min-w-0" }, [
        h("div", { class: "text-xs text-muted" }, cprops.label),
        h("div", { class: "font-bold truncate" }, p.name),
        phone ? h("div", { class: "text-sm text-muted" }, h("bdi", null, phone)) : null,
      ]),
    ]),
    phone
      ? h("div", { class: "grid grid-cols-2 gap-3" }, [
          h(
            "a",
            { href: "tel:" + phone, class: "btn btn-primary", style: "text-decoration: none" },
            [h(Icon, { name: "phone", size: 18 }), " " + t("common.call")]
          ),
          h(
            "a",
            {
              href: waLink(phone),
              target: "_blank",
              rel: "noopener",
              class: "btn btn-accent",
              style: "text-decoration: none",
            },
            [h(Icon, { name: "message", size: 18 }), " " + t("common.whatsapp")]
          ),
        ])
      : null,
  ]);
};
</script>
