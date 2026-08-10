<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <LoadingState v-if="profile.loading" :label="t('common.loading')" />

    <LoadError
      v-else-if="profile.error"
      :title="t('errors.loadFailed')"
      :detail="loadErrorMessage"
      :hint="t('errors.retryHint')"
      :retry-label="t('common.retry')"
      @retry="profile.reload()"
    />

    <template v-else-if="profile.data && profile.data.name">
      <section class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-12 w-12 text-lg"
            style="background: var(--c-primary); color: var(--c-primary-ink)"
          >
            {{ initial }}
          </span>
          <div class="min-w-0">
            <div class="text-lg font-bold leading-tight truncate">
              {{ profile.data.full_name || t("common.none") }}
            </div>
            <StatusLabel class="mt-1" :label="profile.data.status || t('common.none')" :tone="statusTone" />
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

      <Panel
        v-if="profile.data.license_number || profile.data.license_expiry"
        :title="t('home.license')"
      >
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

        <Button
          v-if="licenseDue"
          class="mt-3"
          variant="outline"
          size="xl"
          :disabled="renewal.loading"
          :loading="renewal.loading"
          :label="t('profile.requestRenewal')"
          @click="requestRenewal"
        >
          <template #prefix><Icon name="alert" :size="18" /></template>
        </Button>
      </Panel>

      <Panel v-if="documents.length" :title="t('profile.documents')">
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
      </Panel>

      <Panel v-if="clearanceRow" :title="t('clearance.title')">
        <template #status>
          <StatusLabel :label="clearanceStatusLabel" :tone="clearanceTone" />
        </template>
        <dl class="space-y-2 text-sm">
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
        <Button
          v-if="clearanceRow.issued"
          type="button"
          :disabled="certificate.loading"
          class="mt-3"
          variant="solid"
          theme="green"
          size="xl"
          :loading="certificate.loading"
          :label="t('clearance.downloadCertificate')"
          @click="downloadClearanceCertificate"
        >
          <template #prefix><Icon name="badge" :size="18" /></template>
        </Button>
      </Panel>

      <Panel :title="t('profile.more')">
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
      </Panel>

      <Panel :title="t('profile.myRequests')">
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
      </Panel>

      <Panel :title="t('lang.label')">
        <div class="flex items-center gap-2">
          <Icon name="globe" :size="18" class="text-primary shrink-0" />
          <div class="ms-auto"><LangToggle /></div>
        </div>
      </Panel>

      <Panel v-if="canOfferPush" :title="t('push.title')">
        <div class="flex items-center gap-2">
          <Icon name="bell" :size="18" class="text-primary shrink-0" />
          <div class="min-w-0 text-xs text-muted">{{ t("push.body") }}</div>
          <Button
            type="button"
            class="ms-auto shrink-0"
            :variant="isSubscribed ? 'outline' : 'solid'"
            :theme="isSubscribed ? 'gray' : 'green'"
            size="lg"
            :disabled="isBusy"
            :loading="isBusy"
            :label="isSubscribed ? t('push.disable') : t('push.enable')"
            @click="togglePush"
          />
        </div>
        <div v-if="isDenied" class="text-xs text-warning mt-2">{{ t("push.denied") }}</div>
      </Panel>
    </template>

    <EmptyState v-else :title="t('profile.empty')">
      <template #icon><Icon name="user" :size="22" /></template>
    </EmptyState>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { Button, createResource } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
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

const moreLinks = [
  { to: "/vehicle", icon: "truck", labelKey: "home.myVehicle" },
];

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

const loadErrorMessage = computed(() => resourceErrorMessage(profile.error, "errors.loadFailed"));

const clearance = createResource({
  url: "apex.salis.api.driver_portal.my_clearance",
  auto: true,
});
const clearanceRow = computed(() => (clearance.data?.has_clearance ? clearance.data : null));
const certificate = createResource({
  url: "apex.salis.api.driver_portal.get_my_clearance_certificate",
  method: "POST",
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});

/* The print key is minted by a POST, so the URL only exists after the round trip — and a
   window opened from that callback is outside the gesture and blocked on both mobile
   browsers. The tab is claimed on the tap and navigated when the answer lands. */
function downloadClearanceCertificate() {
  const tab = window.open("", "_blank");
  if (tab) tab.opener = null;
  certificate.submit(
    {},
    {
      onSuccess: (data) => {
        const url = data?.certificate_url;
        if (!url) {
          if (tab) tab.close();
          return;
        }
        if (tab) tab.location.href = url;
        else window.open(url, "_blank", "noopener");
      },
      onError: () => {
        if (tab) tab.close();
      },
    },
  );
}

const documents = computed(() => profile.data?.documents || []);

const initial = computed(
  () => ((profile.data?.full_name || "?").trim().charAt(0).toUpperCase()) || "?",
);

const statusTone = computed(() => {
  const s = (profile.data?.status || "").toLowerCase();
  if (s === "active") return "success";
  if (s === "released" || s === "stopped") return "danger";
  if (s === "on leave") return "warning";
  return "neutral";
});

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

const clearanceTone = computed(() => {
  const s = (clearanceRow.value?.status || "").toLowerCase();
  if (s === "cleared") return "success";
  if (s === "blocked") return "danger";
  if (s === "in progress") return "warning";
  return "neutral";
});
const clearanceStatusLabel = computed(() => {
  const c = clearanceRow.value;
  if (!c) return "";
  if (c.issued) return t("clearance.issued");
  if (c.blocked) return t("clearance.blocked");
  return c.status || t("common.none");
});
</script>
