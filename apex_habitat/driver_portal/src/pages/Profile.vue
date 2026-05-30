<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("profile.title") }}</h2>

    <div v-if="profile.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

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
            <dd class="ms-auto font-semibold">{{ profile.data.phone }}</dd>
          </div>
          <div class="flex items-center gap-2">
            <Icon name="truck" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.currentVehicle") }}</dt>
            <dd class="ms-auto font-semibold">{{ profile.data.current_vehicle || t("common.notAssigned") }}</dd>
          </div>
          <div v-if="profile.data.project" class="flex items-center gap-2">
            <Icon name="briefcase" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.project") }}</dt>
            <dd class="ms-auto font-semibold">{{ profile.data.project }}</dd>
          </div>
          <div v-if="profile.data.employee" class="flex items-center gap-2">
            <Icon name="user" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("profile.employee") }}</dt>
            <dd class="ms-auto font-semibold">{{ profile.data.employee }}</dd>
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
            <dd class="ms-auto font-semibold">{{ profile.data.license_number }}</dd>
          </div>
          <div v-if="profile.data.license_expiry" class="flex items-center gap-2" :class="licenseColor">
            <Icon :name="licenseIcon" :size="18" class="shrink-0" />
            <dt class="text-muted">{{ t("profile.licenseExpiry") }}</dt>
            <dd class="ms-auto font-semibold">
              {{ profile.data.license_expiry }}
              <span v-if="licenseHint" class="opacity-90">· {{ licenseHint }}</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- Language selector lives on the profile too (besides the header). -->
      <section class="card card-pad">
        <div class="flex items-center gap-2">
          <Icon name="globe" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t("lang.label") }}</span>
          <div class="ms-auto"><LangToggle /></div>
        </div>
      </section>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("profile.empty") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LangToggle from "../components/LangToggle.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const profile = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_profile",
  auto: true,
});

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
</script>
