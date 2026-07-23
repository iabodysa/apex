<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <!-- Driver identity (compact). -->
    <section class="card card-pad">
      <div class="flex items-center gap-3">
        <span
          class="avatar h-12 w-12 text-lg"
          style="background: var(--c-primary); color: var(--c-primary-ink)"
        >
          {{ initial }}
        </span>
        <div class="min-w-0">
          <div class="text-lg font-extrabold leading-tight truncate">
            {{ ctx.driver.full_name }}
          </div>
          <span class="pill mt-1" :class="statusPill">{{ ctx.driver.status || "—" }}</span>
        </div>
      </div>
    </section>

    <!-- TODAY: attendance state + single context action (check in -> check out -> done). -->
    <section class="card card-pad space-y-3">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-wider text-soft">{{ t("home.today") }}</p>
          <p class="text-base font-extrabold leading-tight">{{ attendanceLine }}</p>
        </div>
        <span class="pill shrink-0" :class="attendancePill">{{ attendanceState }}</span>
      </div>

      <!-- Done is a non-interactive state; check-in/out route to the guarded flow. -->
      <div v-if="attendanceStep === 'done'" class="btn btn-outline" aria-disabled="true">
        <Icon name="badge" :size="20" /> {{ t("home.doneForToday") }}
      </div>
      <router-link v-else to="/attendance" class="btn btn-primary">
        <Icon name="calendar" :size="20" />
        {{ attendanceStep === "out" ? t("home.checkOutNow") : t("home.checkInNow") }}
      </router-link>
    </section>

    <!-- Alert chips: license near/over expiry, no vehicle, open clearance. -->
    <section v-if="alertChips.length" class="flex flex-wrap gap-2">
      <span
        v-for="chip in alertChips"
        :key="chip.key"
        class="pill"
        :class="chip.tone"
      >
        <Icon :name="chip.icon" :size="14" />
        {{ chip.label }}
      </span>
    </section>

    <!-- NEXT TRIP strip: earliest not-done trip with depart + route + action. -->
    <section class="card card-pad">
      <p class="text-xs font-semibold uppercase tracking-wider text-soft mb-2">{{ t("home.nextTrip") }}</p>
      <template v-if="nextTrip">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-bold leading-tight truncate">
              <bdi>{{ nextTrip.route_plan || nextTrip.name }}</bdi>
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-soft">
              <span v-if="nextTrip.vehicle" class="inline-flex items-center gap-1">
                <Icon name="truck" :size="14" class="text-primary shrink-0" /><bdi>{{ nextTrip.vehicle }}</bdi>
              </span>
              <span v-if="nextTrip.depart_time">
                {{ t("home.depart") }} <bdi>{{ fmtTime(nextTrip.depart_time) }}</bdi>
              </span>
              <span v-if="nextTrip.return_time">
                · {{ t("home.return") }} <bdi>{{ fmtTime(nextTrip.return_time) }}</bdi>
              </span>
            </div>
          </div>
          <router-link
            :to="'/route/' + encodeURIComponent(nextTrip.name)"
            class="pill pill-accent shrink-0"
          >
            {{ t("home.viewTrip") }} <Icon name="chevron" :size="14" />
          </router-link>
        </div>
        <!-- One-tap navigation to the next trip's first stop (same deep-link as Route). -->
        <a
          v-if="nextTrip.google_maps_url"
          :href="nextTrip.google_maps_url"
          target="_blank"
          rel="noopener"
          class="text-primary text-sm inline-flex items-center gap-1 mt-2"
        >
          <Icon name="map-pin" :size="14" /> {{ t("route.openMap") }}
        </a>
      </template>
      <p v-else class="text-sm text-muted">{{ t("home.noTripToday") }}</p>
    </section>

    <!-- NOTIFICATIONS strip (native Notification Log) with a promoted licence banner. -->
    <section v-if="licenseBanner || notifications.length" class="card card-pad space-y-3">
      <p class="text-xs font-semibold uppercase tracking-wider text-soft">{{ t("notifications.title") }}</p>

      <!-- Licence-expiry banner promoted client-side from the days-to-expiry. -->
      <div v-if="licenseBanner" class="flex items-center gap-2 text-sm" :class="licenseBanner.tone">
        <Icon name="alert" :size="16" class="shrink-0" />
        <span>{{ licenseBanner.label }}</span>
      </div>

      <ul v-if="notifications.length" class="space-y-2">
        <li v-for="note in notifications" :key="note.name" class="flex items-start gap-2 text-sm">
          <Icon name="alert" :size="16" class="text-primary shrink-0 mt-0.5" :class="{ 'opacity-50': note.read }" />
          <div class="min-w-0">
            <p class="font-semibold leading-tight" :class="{ 'text-muted': note.read }">{{ note.subject }}</p>
            <p v-if="note.body" class="text-xs text-muted leading-snug">{{ note.body }}</p>
          </div>
        </li>
      </ul>
    </section>

    <!-- MORE: the full action grid, demoted below the primary cards. -->
    <section>
      <h2 class="section-title mb-3">{{ t("home.more") }}</h2>
      <div class="grid grid-cols-2 gap-3">
        <router-link
          v-for="a in actions"
          :key="a.to"
          :to="a.to"
          class="quick-action"
          :style="a.style"
        >
          <Icon :name="a.icon" :size="26" />
          <span class="font-bold">{{ t(a.labelKey) }}</span>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t, n, fmtTime } = useI18n();

const props = defineProps({ ctx: { type: Object, required: true } });

const initial = computed(
  () => (props.ctx.driver.full_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const statusPill = computed(() => {
  const s = (props.ctx.driver.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "suspended" || s === "blocked" || s === "inactive") return "pill-danger";
  return "pill-neutral";
});

// One composite "today" read (attendance + next trip + license + vehicle/clearance
// flags) so the dashboard paints in a single round-trip. Server-computed, no math.
const today = createResource({
  url: "apex.salis.api.driver_portal.get_my_today",
  auto: true,
});
const td = computed(() => today.data || {});

// Native Notification Log rows for this user (identity-scoped server-side).
const notes = createResource({
  url: "apex.salis.api.driver_portal.get_my_notifications",
  auto: true,
});
const notifications = computed(() => notes.data || []);

// --- Today attendance: single context step (check-in -> check-out -> done). ---
const attendanceStep = computed(() => {
  const a = td.value.attendance || {};
  if (a.checked_out) return "done";
  if (a.checked_in) return "out";
  return "in";
});
const attendanceLine = computed(() => {
  const a = td.value.attendance || {};
  if (a.checked_in && a.check_in) return t("home.checkedInAt", { time: fmtTime(a.check_in) });
  return t("home.notCheckedIn");
});
const attendanceState = computed(() => {
  const step = attendanceStep.value;
  if (step === "done") return t("attendance.checkedOutLabel");
  if (step === "out") return t("attendance.checkedInLabel");
  return t("attendance.notCheckedIn");
});
const attendancePill = computed(() =>
  attendanceStep.value === "in" ? "pill-neutral" : "pill-success",
);

// --- Next trip (already labelled + filtered to not-done by the server). ---
const nextTrip = computed(() => td.value.next_trip || null);

// --- License countdown (server-computed days/state). ---
const license = computed(() => td.value.license || {});

// --- Alert chips: license, no-vehicle, open clearance. ---
const alertChips = computed(() => {
  const chips = [];
  const lic = license.value;
  if (lic.state === "expired") {
    chips.push({ key: "lic", icon: "alert", tone: "pill-danger", label: t("home.alertLicenseExpired") });
  } else if (lic.state === "expiring" && lic.days_to_expiry != null) {
    chips.push({
      key: "lic",
      icon: "alert",
      tone: "pill-warning",
      label: t("home.alertLicense", { n: n(lic.days_to_expiry) }),
    });
  }
  if (td.value.vehicle_bound === false) {
    chips.push({ key: "veh", icon: "truck", tone: "pill-warning", label: t("home.alertNoVehicle") });
  }
  if (td.value.open_clearance) {
    chips.push({ key: "clr", icon: "shield", tone: "pill-danger", label: t("home.alertClearance") });
  }
  return chips;
});

// Licence-expiry banner promoted into the notifications strip: a single, prominent
// line derived client-side from the same days-to-expiry the chip uses.
const licenseBanner = computed(() => {
  const lic = license.value;
  if (lic.state === "expired") return { tone: "text-danger", label: t("home.alertLicenseExpired") };
  if (lic.state === "expiring" && lic.days_to_expiry != null) {
    return { tone: "text-warning", label: t("home.alertLicense", { n: n(lic.days_to_expiry) }) };
  }
  return null;
});

// The full action grid, demoted under "More". Fuel/Support live under Profile >
// My Requests; not duplicated here.
const actions = [
  {
    to: "/attendance",
    icon: "calendar",
    labelKey: "home.attendance",
    style: "background: var(--c-primary); color: var(--c-primary-ink);",
  },
  {
    to: "/trips",
    icon: "route",
    labelKey: "home.myTrips",
    style: "background: var(--c-ink); color: var(--c-surface);",
  },
  {
    to: "/route",
    icon: "route",
    labelKey: "home.myRoute",
    style: "background: var(--c-mint); color: var(--c-ink);",
  },
  {
    to: "/vehicle",
    icon: "truck",
    labelKey: "home.myVehicle",
    style:
      "background: var(--c-surface); color: var(--c-ink); border: var(--border-width) solid var(--c-border);",
  },
  {
    to: "/profile",
    icon: "user",
    labelKey: "home.profile",
    style:
      "background: var(--c-surface); color: var(--c-ink); border: var(--border-width) solid var(--c-border);",
  },
];
</script>

<style scoped>
.stale-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg, #fef3c7);
  color: var(--c-warning, #92400e);
}
</style>
