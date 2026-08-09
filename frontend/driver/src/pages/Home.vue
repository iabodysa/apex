<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <TodaySkeleton v-if="loading" :label="t('home.loadingLabel')" />

  <LoadError
    v-else-if="today.error"
    :title="t('errors.todayFailed')"
    :detail="loadErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="reload"
  />

  <div v-else class="field-runway">
    <DecisionStage
      class="field-stage"
      :eyebrow="t('home.today')"
      :title="t('home.step.' + step.key)"
      :subtitle="t('home.stepHint.' + step.key)"
    >
      <ShiftCard :today="td" />
      <NextTripCard :trip="nextTrip" />

      <template #footer>
        <ActionDock>
          <template #primary>
            <Button
              class="dock-btn"
              variant="solid"
              theme="green"
              size="2xl"
              :disabled="!step.to"
              :label="t('home.step.' + step.key)"
              @click="go"
            >
              <template #prefix><Icon :name="stepIcon" :size="20" /></template>
            </Button>
          </template>
        </ActionDock>
      </template>
    </DecisionStage>

    <aside class="field-evidence">
      <AlertsCard v-if="alerts.length" :alerts="alerts" />
      <NotificationsCard :notifications="notifications" />
    </aside>

    <DestinationsCard class="field-ledger" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Button, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import DecisionStage from "@shared/components/DecisionStage.vue";
import TodaySkeleton from "../components/TodaySkeleton.vue";
import LoadError from "@shared/components/LoadError.vue";
import ShiftCard from "../components/ShiftCard.vue";
import AlertsCard from "../components/AlertsCard.vue";
import NextTripCard from "../components/NextTripCard.vue";
import NotificationsCard from "../components/NotificationsCard.vue";
import DestinationsCard from "../components/DestinationsCard.vue";
import Icon from "../components/Icon.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { useToday, nextStep } from "../today";

const { t, n } = useI18n();
const router = useRouter();

const today = useToday();
const td = computed(() => today.data || {});

const notes = createResource({
  url: "apex.salis.api.driver_portal.get_my_notifications",
  auto: true,
});
const notifications = computed(() => notes.data || []);

const loading = computed(() => today.loading && !today.data);
const loadErrorMessage = computed(() => resourceErrorMessage(today.error, "errors.todayFailed"));

function reload() {
  today.reload();
  notes.reload();
}

const nextTrip = computed(() => td.value.next_trip || null);

const step = computed(() => nextStep(td.value));

const STEP_ICONS = {
  checkIn: "calendar",
  checkOut: "calendar",
  openTrip: "route",
  resumeTrip: "route",
  done: "badge",
};
const stepIcon = computed(() => STEP_ICONS[step.value.key]);

function go() {
  if (step.value.to) router.push(step.value.to);
}

const alerts = computed(() => {
  const rows = [];
  const license = td.value.license || {};
  if (license.state === "expired") {
    rows.push({
      key: "license",
      icon: "alert",
      tone: "danger",
      label: t("home.alertLicenseExpired"),
      badge: t("home.badgeBlocking"),
    });
  } else if (license.state === "expiring" && license.days_to_expiry != null) {
    rows.push({
      key: "license",
      icon: "alert",
      tone: "warning",
      label: t("home.alertLicense", { n: n(license.days_to_expiry) }),
      badge: t("home.badgeSoon"),
    });
  }
  if (td.value.vehicle_bound === false) {
    rows.push({
      key: "vehicle",
      icon: "truck",
      tone: "warning",
      label: t("home.alertNoVehicle"),
      badge: t("home.badgeSoon"),
    });
  }
  if (td.value.open_clearance) {
    rows.push({
      key: "clearance",
      icon: "shield",
      tone: "danger",
      label: t("home.alertClearance"),
      badge: t("home.badgeBlocking"),
    });
  }
  return rows;
});
</script>
