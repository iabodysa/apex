<template>
  <div class="space-y-5">
    <!-- Driver summary -->
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

      <div class="divider my-4"></div>

      <div class="space-y-3 text-sm">
        <div class="flex items-center gap-2">
          <Icon name="truck" :size="18" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("home.vehicle") }}</span>
          <span class="ms-auto font-semibold">{{ ctx.driver.current_vehicle || t("common.notAssigned") }}</span>
        </div>
        <div v-if="ctx.driver.license_expiry" class="flex items-center gap-2" :class="licenseColor">
          <Icon :name="licenseIcon" :size="18" class="shrink-0" />
          <span class="text-muted">{{ t("home.license") }}</span>
          <span class="ms-auto font-semibold">
            {{ ctx.driver.license_expiry }}
            <span v-if="licenseHint" class="opacity-90">· {{ licenseHint }}</span>
          </span>
        </div>
      </div>
    </section>

    <!-- Quick actions -->
    <section>
      <h2 class="section-title mb-3">{{ t("home.quickActions") }}</h2>
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
import { computed } from "vue";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

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

// Days until the license expires (null when unknown) -> drives colour + hint.
const daysToExpiry = computed(() => {
  const v = props.ctx.driver.license_expiry;
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

// Token-driven action tiles (flat fills, brand colours).
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
    to: "/vehicle",
    icon: "truck",
    labelKey: "home.myVehicle",
    style: "background: var(--c-mint); color: var(--c-ink);",
  },
  {
    to: "/fuel",
    icon: "fuel",
    labelKey: "home.requestFuel",
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
  {
    to: "/tickets",
    icon: "help",
    labelKey: "home.support",
    style:
      "background: var(--c-surface); color: var(--c-ink); border: var(--border-width) solid var(--c-border);",
  },
];
</script>
