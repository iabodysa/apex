<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("vehicle.title") }}</h2>

    <LoadingState v-if="vehicle.loading" :label="t('common.loading')" />

    <ErrorState v-else-if="vehicle.error" :message="t('errors.loadFailed')" @retry="vehicle.reload()" />

    <template v-else-if="v">
      <!-- Identity card: plate + live operational status -->
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

        <dl v-if="hasDetails" class="space-y-3 text-sm">
          <div v-if="v.vehicle_category" class="flex items-center gap-2">
            <Icon name="layers" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.category") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.vehicle_category }}</dd>
          </div>
          <div v-if="odometer != null" class="flex items-center gap-2">
            <Icon name="gauge" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.odometer") }}</dt>
            <dd class="ms-auto font-semibold">
              <bdi>{{ odometer }}</bdi> {{ t("vehicle.km") }}
            </dd>
          </div>
          <div v-if="v.planned_fuel_grade" class="flex items-center gap-2">
            <Icon name="fuel" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.fuelGrade") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.planned_fuel_grade }}</dd>
          </div>
        </dl>
      </section>

      <!-- Documents & expiry: registration / insurance / inspection, each with
           an amber (<=30d) / red (expired) warning. Server computes the state. -->
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

      <!-- Assignment: where the vehicle belongs + since when -->
      <section v-if="v.project || v.assignment_start" class="card card-pad">
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
        </dl>
      </section>

      <!-- Report a problem with the bound vehicle (creates a Vehicle Issue). -->
      <section class="card card-pad space-y-3">
        <button v-if="!reporting" class="btn btn-outline" @click="reporting = true">
          <Icon name="alert" :size="18" /> {{ t("vehicle.reportProblem") }}
        </button>
        <template v-else>
          <textarea
            v-model="problem"
            :placeholder="t('vehicle.problemPlaceholder')"
            class="textarea"
          ></textarea>
          <div class="flex gap-2">
            <button class="btn btn-primary" :disabled="report.loading || !problem.trim()" @click="submitProblem">
              <Icon name="help" :size="18" /> {{ t("vehicle.send") }}
            </button>
            <button class="btn btn-outline" @click="reporting = false">{{ t("vehicle.cancel") }}</button>
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
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t } = useI18n();

const vehicle = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_my_vehicle",
  auto: true,
});

// Report-a-problem: a Vehicle Issue prefilled server-side with the bound vehicle.
const reporting = ref(false);
const problem = ref("");
const report = createResource({
  url: "apex_habitat.salis.api.driver_portal.report_vehicle_problem",
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

// Odometer is an Int that defaults to 0; treat a real reading (> 0) as present
// and a bare 0 as "not recorded" so the row is omitted rather than showing 0 km.
const odometer = computed(() => {
  const o = v.value?.odometer;
  return o != null && o > 0 ? o.toLocaleString("en-US") : null;
});

const hasDetails = computed(
  () => !!(v.value?.vehicle_category || odometer.value != null || v.value?.planned_fuel_grade),
);

const compliance = computed(() => v.value?.compliance || []);

const statusPill = computed(() => {
  const s = (v.value?.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "released" || s === "stopped") return "pill-danger";
  if (s === "under maintenance") return "pill-warning";
  return "pill-neutral";
});

// Map a compliance_type Select value to its localized label.
const COMPLIANCE_LABELS = {
  "Registration (Istimara)": "vehicle.registration",
  Insurance: "vehicle.insurance",
  "Periodic Inspection": "vehicle.inspection",
};
function complianceLabel(type) {
  const key = COMPLIANCE_LABELS[type];
  return key ? t(key) : type;
}

// Server gives us state ("expired" | "expiring" | "valid") + signed days_to_expiry,
// so the SPA does no date math (no timezone drift, identical in both languages).
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
