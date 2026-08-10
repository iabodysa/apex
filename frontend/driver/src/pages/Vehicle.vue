<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <LoadingState v-if="vehicle.loading" :label="t('common.loading')" />

    <ErrorState v-else-if="vehicle.error" :message="t('errors.loadFailed')" @retry="vehicle.reload()" />

    <template v-else-if="v">
      <section class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-12 w-12"
            style="border-radius: var(--radius); background: var(--c-ink); color: var(--c-surface)"
          >
            <Icon name="truck" :size="26" />
          </span>
          <div class="min-w-0">
            <div class="text-lg font-extrabold leading-tight truncate">
              <bdi>{{ v.plate_number || v.name }}</bdi>
            </div>
            <span class="pill mt-1" :class="statusPill">{{ v.status || t("common.none") }}</span>
          </div>
        </div>

        <div v-if="hasDetails" class="divider my-4"></div>

        <VehicleFacts v-if="hasDetails" :facts="vehicleFacts" :empty-value="t('common.none')">
          <template #icon="{ fact }">
            <Icon v-if="fact.icon" :name="fact.icon" :size="18" class="text-primary shrink-0" />
          </template>
        </VehicleFacts>
      </section>

      <section v-if="compliance.length" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
          {{ t("vehicle.compliance") }}
        </h3>
        <dl class="space-y-3 text-sm">
          <div
            v-for="doc in compliance"
            :key="doc.compliance_type"
            class="flex items-center gap-2"
            :class="expiryColor(doc)"
          >
            <Icon :name="expiryIcon(doc)" :size="18" class="shrink-0" />
            <dt class="min-w-0">
              <span class="font-semibold">{{ complianceLabel(doc.compliance_type) }}</span>
              <span class="text-muted block text-xs">
                <bdi>{{ doc.document_number || t("vehicle.noDocNumber") }}</bdi>
              </span>
            </dt>
            <dd class="ms-auto text-end shrink-0">
              <span class="font-semibold"><bdi>{{ doc.expiry_date }}</bdi></span>
              <span class="block text-xs opacity-90">{{ expiryHint(doc) }}</span>
            </dd>
          </div>
        </dl>
      </section>

      <section v-if="v.project || v.assignment_start || v.last_site_maps_url" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
          {{ t("home.myVehicle") }}
        </h3>
        <dl class="space-y-3 text-sm">
          <div v-if="v.project" class="flex items-center gap-2">
            <Icon name="briefcase" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.project") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.project }}</dd>
          </div>
          <div v-if="v.assignment_start" class="flex items-center gap-2">
            <Icon name="calendar" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.assignmentStart") }}</dt>
            <dd class="ms-auto font-semibold"><bdi>{{ v.assignment_start }}</bdi></dd>
          </div>
          <div v-if="v.last_site_maps_url" class="flex items-center gap-2">
            <Icon name="map-pin" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.lastSite") }}</dt>
            <a
              :href="v.last_site_maps_url"
              target="_blank"
              rel="noopener"
              class="ms-auto text-primary font-semibold inline-flex items-center gap-1"
            >
              <Icon name="external" :size="14" /> {{ t("route.openMap") }}
            </a>
          </div>
        </dl>
      </section>

      <section class="card card-pad space-y-3">
        <Button v-if="!reporting" variant="outline" size="xl" :label="t('vehicle.reportProblem')" @click="reporting = true">
          <template #prefix><Icon name="alert" :size="18" /></template>
        </Button>
        <template v-else>
          <FormControl
            v-model="problem"
            type="textarea"
            size="lg"
            :rows="4"
            :label="t('vehicle.problemSubject')"
            :placeholder="t('vehicle.problemPlaceholder')"
          />
          <div class="flex gap-2">
            <Button variant="solid" theme="green" size="xl" :disabled="report.loading || !problem.trim()" :loading="report.loading" :label="t('vehicle.send')" @click="submitProblem">
              <template #prefix><Icon name="help" :size="18" /></template>
            </Button>
            <Button variant="outline" size="xl" :label="t('vehicle.cancel')" @click="reporting = false" />
          </div>
        </template>
      </section>
    </template>

    <EmptyState
      v-else
      icon="truck"
      :title="t('vehicle.empty')"
      :hint="t('vehicle.emptyHint')"
    />
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import VehicleFacts from "@shared/components/VehicleFacts.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t } = useI18n();

const vehicle = createResource({
  url: "apex.salis.api.driver_portal.get_my_vehicle",
  auto: true,
});

const reporting = ref(false);
const problem = ref("");
const report = createResource({
  url: "apex.salis.api.driver_portal.report_vehicle_problem",
  onSuccess: () => {
    pushToast(t("vehicle.problemSent"), "ok");
    problem.value = "";
    reporting.value = false;
  },
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
function submitProblem() {
  if (!problem.value.trim()) return;
  report.submit({ subject: t("vehicle.problemSubject"), description: problem.value.trim() });
}

const v = computed(() => vehicle.data?.vehicle || null);

const odometer = computed(() => {
  const o = v.value?.odometer;
  return o != null && o > 0 ? o.toLocaleString("en-US") : null;
});

const hasDetails = computed(
  () => !!(v.value?.vehicle_category || odometer.value != null || v.value?.planned_fuel_grade),
);

const vehicleFacts = computed(() =>
  [
    v.value?.vehicle_category && {
      key: "category",
      icon: "layers",
      label: t("vehicle.category"),
      value: v.value.vehicle_category,
    },
    odometer.value != null && {
      key: "odometer",
      icon: "gauge",
      label: t("vehicle.odometer"),
      value: odometer.value,
      suffix: t("vehicle.km"),
      numeric: true,
    },
    v.value?.planned_fuel_grade && {
      key: "grade",
      icon: "fuel",
      label: t("vehicle.fuelGrade"),
      value: v.value.planned_fuel_grade,
    },
  ].filter(Boolean),
);

const compliance = computed(() => v.value?.compliance || []);

const statusPill = computed(() => {
  const s = (v.value?.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "released" || s === "stopped") return "pill-danger";
  if (s === "under maintenance") return "pill-warning";
  return "pill-neutral";
});

const COMPLIANCE_LABELS = {
  "Registration (Istimara)": "vehicle.registration",
  Insurance: "vehicle.insurance",
  "Periodic Inspection": "vehicle.inspection",
};
function complianceLabel(type) {
  const key = COMPLIANCE_LABELS[type];
  return key ? t(key) : type;
}

function expiryColor(doc) {
  if (doc.state === "expired") return "text-danger";
  if (doc.state === "expiring") return "text-warning";
  return "";
}
function expiryIcon(doc) {
  if (doc.state === "expired") return "alert";
  if (doc.state === "expiring") return "alert";
  return "shield";
}
function expiryHint(doc) {
  const d = doc.days_to_expiry;
  if (doc.state === "expired") {
    return d === 0 ? t("vehicle.expired") : t("vehicle.expiredAgo", { n: Math.abs(d) });
  }
  if (doc.state === "expiring") {
    return d === 0 ? t("vehicle.expiresToday") : t("vehicle.expiringSoon", { n: d });
  }
  return t("vehicle.valid");
}
</script>
