<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("profile.title") }}</h2>

    <LoadingState v-if="profile.loading" :label="t('common.loading')" />

    <ErrorState v-else-if="profile.error" :message="t('errors.loadFailed')" @retry="profile.reload()" />

    <template v-else-if="profile.data && profile.data.name">
      <!-- Identity card -->
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
              {{ profile.data.full_name || t("common.none") }}
            </div>
            <span class="pill mt-1" :class="statusPill">{{ profile.data.status || t("common.none") }}</span>
          </div>
        </div>

        <div class="divider my-4"></div>

        <dl class="space-y-3 text-sm">
          <div v-if="profile.data.phone" class="flex items-center gap-2">
            <Icon name="phone" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.phone") }}</dt>
            <dd class="ms-auto font-semibold"><bdi>{{ profile.data.phone }}</bdi></dd>
          </div>
          <div class="flex items-center gap-2">
            <Icon name="truck" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.currentVehicle") }}</dt>
            <dd class="ms-auto font-semibold"><bdi>{{ profile.data.current_vehicle || t("common.notAssigned") }}</bdi></dd>
          </div>
          <div v-if="profile.data.project" class="flex items-center gap-2">
            <Icon name="briefcase" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.project") }}</dt>
            <dd class="ms-auto font-semibold">{{ profile.data.project }}</dd>
          </div>
          <div v-if="profile.data.employee" class="flex items-center gap-2">
            <Icon name="user" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.employee") }}</dt>
            <dd class="ms-auto font-semibold"><bdi>{{ profile.data.employee }}</bdi></dd>
          </div>
        </dl>
      </section>

      <!-- License card (reuses the expiry colour/warning logic) -->
      <section v-if="profile.data.license_number || profile.data.license_expiry" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
          {{ t("home.license") }}
        </h3>
        <dl class="space-y-3 text-sm">
          <div v-if="profile.data.license_number" class="flex items-center gap-2">
            <Icon name="badge" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.licenseNumber") }}</dt>
            <dd class="ms-auto font-semibold"><bdi>{{ profile.data.license_number }}</bdi></dd>
          </div>
          <div v-if="profile.data.license_expiry" class="flex items-center gap-2" :class="licenseColor">
            <Icon :name="licenseIcon" :size="18" class="shrink-0" />
            <dt class="text-muted">{{ t("profile.licenseExpiry") }}</dt>
            <dd class="ms-auto font-semibold">
              <bdi>{{ profile.data.license_expiry }}</bdi>
              <span v-if="licenseHint" class="opacity-90">· {{ licenseHint }}</span>
            </dd>
          </div>
        </dl>

        <!-- Renewal action surfaces only when the licence is near/over expiry. -->
        <button
          v-if="licenseDue"
          class="btn btn-outline mt-3"
          :disabled="renewal.loading"
          @click="requestRenewal"
        >
          <Icon name="alert" :size="18" /> {{ t("profile.requestRenewal") }}
        </button>
      </section>

      <!-- Identity documents: Iqama / passport expiry from the linked Employee
           (server reads them defensively; omitted when none are on file). -->
      <section v-if="documents.length" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
          {{ t("profile.documents") }}
        </h3>
        <dl class="space-y-3 text-sm">
          <div
            v-for="docu in documents"
            :key="docu.type"
            class="flex items-center gap-2"
            :class="docColor(docu)"
          >
            <Icon :name="docIcon(docu)" :size="18" class="shrink-0" />
            <dt class="min-w-0">
              <span class="font-semibold">{{ docLabel(docu.type) }}</span>
              <span v-if="docu.number" class="text-muted block text-xs"><bdi>{{ docu.number }}</bdi></span>
            </dt>
            <dd class="ms-auto text-end shrink-0">
              <span class="font-semibold"><bdi>{{ docu.expiry || t("profile.docNoExpiry") }}</bdi></span>
              <span v-if="docHint(docu)" class="block text-xs opacity-90">{{ docHint(docu) }}</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- Exit clearance: state + blocking items, with the certificate PDF when issued. -->
      <section v-if="clearanceRow" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
          {{ t("clearance.title") }}
        </h3>
        <div class="flex items-center justify-between gap-3">
          <span class="text-sm text-muted">{{ t("clearance.status") }}</span>
          <span class="pill" :class="clearancePill">{{ clearanceStatusLabel }}</span>
        </div>
        <dl class="mt-3 space-y-2 text-sm">
          <div v-if="clearanceRow.clearance_reason" class="flex items-center gap-2">
            <dt class="text-muted">{{ t("clearance.reason") }}</dt>
            <dd class="ms-auto font-semibold">{{ clearanceRow.clearance_reason }}</dd>
          </div>
          <template v-if="clearanceRow.blocked">
            <p class="text-xs text-warning">{{ t("clearance.blockedHint") }}</p>
            <div v-if="clearanceRow.outstanding_fuel_exceptions" class="flex items-center gap-2 text-warning">
              <Icon name="alert" :size="16" class="shrink-0" />
              <dt>{{ t("clearance.openExceptions") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ clearanceRow.outstanding_fuel_exceptions }}</bdi></dd>
            </div>
            <div v-if="clearanceRow.outstanding_recoveries" class="flex items-center gap-2 text-warning">
              <Icon name="alert" :size="16" class="shrink-0" />
              <dt>{{ t("clearance.openRecoveries") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ clearanceRow.outstanding_recoveries }}</bdi></dd>
            </div>
          </template>
        </dl>
        <a
          v-if="clearanceRow.issued && clearanceRow.certificate_url"
          :href="clearanceRow.certificate_url"
          target="_blank"
          rel="noopener"
          class="btn btn-primary mt-3"
        >
          <Icon name="badge" :size="18" /> {{ t("clearance.downloadCertificate") }}
        </a>
      </section>

      <!-- More: the secondary screens that left the bottom bar (Home dashboard,
           Route, Vehicle, Attendance) nest here so the two primary tabs stay
           Trips + Profile while every screen is one tap away. -->
      <div class="space-y-2">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">
          {{ t("profile.more") }}
        </h3>
        <router-link
          v-for="m in moreLinks"
          :key="m.to"
          :to="m.to"
          class="card card-pad flex items-center gap-3"
          style="text-decoration: none"
        >
          <Icon :name="m.icon" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t(m.labelKey) }}</span>
          <Icon name="chevron" :size="18" class="ms-auto text-muted shrink-0" />
        </router-link>
      </div>

      <!-- My Requests: secondary actions reachable from the profile rather
           than the bottom tab bar (fuel request + support tickets). Each row
           is a tappable mini-card, matching the Unlinked screen's link rows. -->
      <div class="space-y-2">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">
          {{ t("profile.myRequests") }}
        </h3>
        <router-link to="/fuel" class="card card-pad flex items-center gap-3" style="text-decoration: none">
          <Icon name="fuel" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t("profile.fuelRequest") }}</span>
          <Icon name="chevron" :size="18" class="ms-auto text-muted shrink-0" />
        </router-link>
        <router-link to="/tickets" class="card card-pad flex items-center gap-3" style="text-decoration: none">
          <Icon name="help" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t("profile.supportTickets") }}</span>
          <Icon name="chevron" :size="18" class="ms-auto text-muted shrink-0" />
        </router-link>
      </div>

      <!-- Language selector lives on the profile too (besides the header). -->
      <section class="card card-pad">
        <div class="flex items-center gap-2">
          <Icon name="globe" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t("lang.label") }}</span>
          <div class="ms-auto"><LangToggle /></div>
        </div>
      </section>

      <!-- Background push opt-in: shown only when the device supports push AND the
           owner enabled+configured VAPID (canOfferPush). Hidden otherwise. -->
      <section v-if="canOfferPush" class="card card-pad">
        <div class="flex items-center gap-2">
          <Icon name="bell" :size="18" class="text-primary shrink-0" />
          <div class="min-w-0">
            <div class="text-sm font-semibold">{{ t("push.title") }}</div>
            <div class="text-xs text-muted">{{ t("push.body") }}</div>
          </div>
          <button
            type="button"
            class="btn btn-sm ms-auto shrink-0"
            :class="isSubscribed ? 'btn-ghost' : 'btn-primary'"
            :disabled="isBusy"
            @click="togglePush"
          >
            {{ isSubscribed ? t("push.disable") : t("push.enable") }}
          </button>
        </div>
        <div v-if="isDenied" class="text-xs text-warning mt-2">{{ t("push.denied") }}</div>
      </section>
    </template>

    <EmptyState v-else :title="t('profile.empty')" />
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LangToggle from "../components/LangToggle.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import {
  initPush,
  enablePush,
  disablePush,
  canOfferPush,
  isSubscribed,
  isBusy,
  isDenied,
} from "../push";

const { t } = useI18n();

// The secondary screens nested under Profile now that the bottom bar is just
// Trips + Profile. Each routes to an existing page; labels reuse the home.* keys.
const moreLinks = [
  { to: "/", icon: "home", labelKey: "profile.dashboard" },
  { to: "/route", icon: "route", labelKey: "home.myRoute" },
  { to: "/vehicle", icon: "truck", labelKey: "home.myVehicle" },
  { to: "/attendance", icon: "calendar", labelKey: "home.attendance" },
];

// Load push config + any existing subscription when the profile opens, so the
// toggle reflects the real state (and stays hidden when push is unconfigured).
onMounted(initPush);

async function togglePush() {
  const ok = isSubscribed.value ? await disablePush() : await enablePush();
  if (ok) pushToast(isSubscribed.value ? t("push.on") : t("push.off"), "ok");
  else if (isDenied.value) pushToast(t("push.denied"), "err");
}

const profile = createResource({
  url: "apex.salis.api.driver_portal.get_driver_profile",
  auto: true,
});

// Exit-clearance state (status, blocking items, certificate URL when issued).
const clearance = createResource({
  url: "apex.salis.api.driver_portal.my_clearance",
  auto: true,
});
const clearanceRow = computed(() => (clearance.data?.has_clearance ? clearance.data : null));

// Identity-document expiries (Iqama/passport) from the linked Employee.
const documents = computed(() => profile.data?.documents || []);

const initial = computed(
  () => ((profile.data?.full_name || "?").trim().charAt(0).toUpperCase()) || "?",
);

const statusPill = computed(() => {
  const s = (profile.data?.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "released" || s === "stopped") return "pill-danger";
  if (s === "on leave") return "pill-warning";
  return "pill-neutral";
});

// Days-until-expiry → colour + hint (mirrors Home.vue's license logic).
const daysToExpiry = computed(() => {
  const v = profile.data?.license_expiry;
  if (!v) return null;
  const exp = new Date(v + "T00:00:00");
  if (isNaN(exp.getTime())) return null;
  const today = new Date(new Date().toDateString());
  return Math.round((exp.getTime() - today.getTime()) / 86400000);
});
const licenseColor = computed(() => {
  const d = daysToExpiry.value;
  if (d === null) return "";
  if (d < 0) return "text-danger";
  if (d <= 30) return "text-warning";
  return "";
});
const licenseIcon = computed(() =>
  daysToExpiry.value !== null && daysToExpiry.value <= 30 ? "alert" : "badge",
);
const licenseHint = computed(() => {
  const d = daysToExpiry.value;
  if (d === null) return "";
  if (d < 0) return t("license.expired");
  if (d <= 30) return t("license.daysLeft", { n: d });
  return "";
});

// Renewal action shows only when the licence is within 30 days or expired —
// the same window the server enforces on request_license_renewal.
const licenseDue = computed(() => {
  const d = daysToExpiry.value;
  return d !== null && d <= 30;
});
const renewal = createResource({
  url: "apex.salis.api.driver_portal.request_license_renewal",
  onSuccess: () => pushToast(t("profile.renewalSent"), "ok"),
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
function requestRenewal() {
  renewal.submit();
}

// Document expiry → colour/icon/hint (same near/over-expiry vocabulary as the
// licence + vehicle compliance; server gives signed days_left).
function docLabel(type) {
  return type === "iqama" ? t("profile.iqama") : t("profile.passport");
}
function docState(docu) {
  const d = docu.days_left;
  if (d == null) return "valid";
  if (d < 0) return "expired";
  if (d <= 30) return "expiring";
  return "valid";
}
function docColor(docu) {
  const s = docState(docu);
  if (s === "expired") return "text-danger";
  if (s === "expiring") return "text-warning";
  return "";
}
function docIcon(docu) {
  return docState(docu) === "valid" ? "badge" : "alert";
}
function docHint(docu) {
  const d = docu.days_left;
  if (d == null) return "";
  if (d < 0) return t("license.expired");
  if (d <= 30) return t("license.daysLeft", { n: d });
  return "";
}

const clearancePill = computed(() => {
  const s = (clearanceRow.value?.status || "").toLowerCase();
  if (s === "cleared") return "pill-success";
  if (s === "blocked") return "pill-danger";
  if (s === "in progress") return "pill-warning";
  return "pill-neutral";
});
const clearanceStatusLabel = computed(() => {
  const c = clearanceRow.value;
  if (!c) return "";
  if (c.issued) return t("clearance.issued");
  if (c.blocked) return t("clearance.blocked");
  return c.status || t("common.none");
});
</script>
