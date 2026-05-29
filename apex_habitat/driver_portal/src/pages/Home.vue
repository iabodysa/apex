<template>
  <div class="space-y-4">
    <!-- Driver header -->
    <section class="bg-ah-surface rounded-ah p-4 shadow-sm">
      <div class="flex items-center gap-3">
        <span
          class="grid place-items-center h-12 w-12 rounded-full bg-ah-primary text-white font-bold text-lg shrink-0"
        >
          {{ initial }}
        </span>
        <div class="min-w-0">
          <div class="text-lg font-bold leading-tight truncate">{{ ctx.driver.full_name }}</div>
          <span
            class="inline-block mt-1 text-xs font-semibold px-2 py-0.5 rounded-full"
            :class="statusClass"
          >
            {{ ctx.driver.status || "—" }}
          </span>
        </div>
      </div>

      <div class="mt-4 space-y-2 text-sm">
        <div class="flex items-center gap-2">
          <Icon name="truck" :size="18" class="text-ah-primary shrink-0" />
          <span class="text-ah-forest/50">Vehicle</span>
          <span class="ml-auto font-medium">{{ ctx.driver.current_vehicle || "Not assigned" }}</span>
        </div>
        <div v-if="ctx.driver.license_expiry" class="flex items-center gap-2" :class="licenseColor">
          <Icon :name="licenseIcon" :size="18" class="shrink-0" />
          <span class="text-ah-forest/50">License</span>
          <span class="ml-auto font-medium">
            {{ ctx.driver.license_expiry }}
            <span v-if="licenseHint" class="opacity-90">· {{ licenseHint }}</span>
          </span>
        </div>
      </div>
    </section>

    <!-- Quick actions -->
    <section class="grid grid-cols-2 gap-3">
      <router-link
        v-for="a in actions"
        :key="a.to"
        :to="a.to"
        class="rounded-ah p-4 flex flex-col gap-3 shadow-sm active:scale-95 transition"
        :class="a.cls"
      >
        <Icon :name="a.icon" :size="26" />
        <span class="font-semibold">{{ a.label }}</span>
      </router-link>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Icon from "../components/Icon.vue";

const props = defineProps({ ctx: { type: Object, required: true } });

const initial = computed(
  () => (props.ctx.driver.full_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const statusClass = computed(() => {
  const s = (props.ctx.driver.status || "").toLowerCase();
  if (s === "active") return "bg-ah-accent/30 text-ah-forest";
  if (s === "suspended" || s === "blocked" || s === "inactive")
    return "bg-ah-danger/15 text-ah-danger";
  return "bg-ah-forest/10 text-ah-forest/70";
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
  if (d === null) return "text-ah-forest/70";
  if (d < 0) return "text-ah-danger";
  if (d <= 30) return "text-ah-warning";
  return "text-ah-forest/70";
});
const licenseIcon = computed(() =>
  daysToExpiry.value !== null && daysToExpiry.value <= 30 ? "alert" : "badge",
);
const licenseHint = computed(() => {
  const d = daysToExpiry.value;
  if (d === null) return "";
  if (d < 0) return "expired";
  if (d <= 30) return `${d} day(s) left`;
  return "";
});

const actions = [
  { to: "/attendance", icon: "calendar", label: "Attendance", cls: "bg-ah-primary text-white" },
  { to: "/trips", icon: "route", label: "My Trips", cls: "bg-ah-forest text-white" },
  { to: "/fuel", icon: "fuel", label: "Request Fuel", cls: "bg-ah-warning text-white" },
  { to: "/tickets", icon: "help", label: "Support", cls: "bg-ah-accent text-ah-forest" },
];
</script>
