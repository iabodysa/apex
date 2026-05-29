<template>
  <div class="min-h-screen bg-ah-sand flex flex-col max-w-md mx-auto font-sans text-ah-forest">
    <div v-if="ctx.loading" class="flex-1 grid place-items-center p-8">
      <div class="text-center text-ah-forest/50">
        <div
          class="animate-spin h-8 w-8 mx-auto rounded-full border-2 border-ah-primary/25 border-t-ah-primary"
        ></div>
        <p class="mt-3 text-sm">Loading…</p>
      </div>
    </div>

    <!-- Linked driver: branded shell with an icon tab bar. -->
    <template v-else-if="linkedDriver">
      <header
        class="sticky top-0 z-10 px-4 py-3 bg-ah-forest text-ah-surface flex items-center justify-between shadow-sm"
      >
        <div class="flex items-center gap-2">
          <span class="text-lg font-extrabold tracking-tight">Salis</span>
          <span class="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/10 text-ah-accent">
            Driver
          </span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium opacity-90 truncate max-w-[8rem]">{{ firstName }}</span>
          <span
            class="grid place-items-center h-8 w-8 rounded-full bg-ah-accent text-ah-forest font-bold text-sm"
          >
            {{ initial }}
          </span>
        </div>
      </header>

      <main class="flex-1 p-4 pb-24"><router-view :ctx="ctx.data" /></main>

      <nav
        class="fixed bottom-0 inset-x-0 max-w-md mx-auto grid grid-cols-5 bg-ah-surface border-t border-ah-forest/10 pb-[env(safe-area-inset-bottom)]"
      >
        <router-link
          v-for="t in tabs"
          :key="t.to"
          :to="t.to"
          class="flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-ah-forest/45"
        >
          <Icon :name="t.icon" :size="22" />
          <span>{{ t.label }}</span>
        </router-link>
      </nav>
    </template>

    <!-- A genuine server error: surface it. Never mis-render as "not linked". -->
    <div v-else-if="ctx.error" class="flex-1 grid place-items-center p-8 text-center">
      <div>
        <div
          class="mx-auto mb-3 h-12 w-12 grid place-items-center rounded-full bg-ah-danger/10 text-ah-danger"
        >
          <Icon name="alert" :size="26" />
        </div>
        <p class="font-bold mb-1">Couldn't load the portal</p>
        <p class="text-sm text-ah-forest/60">{{ ctx.error.message || ctx.error }}</p>
        <button
          class="mt-4 px-5 py-2.5 rounded-ah bg-ah-primary text-white font-semibold active:scale-95 transition"
          @click="ctx.reload()"
        >
          Retry
        </button>
      </div>
    </div>

    <!-- Everyone else (staff or non-staff): a useful screen, never a dead-end. -->
    <Unlinked v-else :ctx="unlinkedCtx" />
  </div>
</template>

<style>
nav .router-link-active {
  color: #00844e;
}
nav .router-link-active svg {
  stroke: #00844e;
}
</style>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";

const ctx = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_context",
  auto: true,
});

const linkedDriver = computed(
  () => ctx.data && ctx.data.enabled && ctx.data.linked && ctx.data.driver,
);

const firstName = computed(
  () => (ctx.data?.driver?.full_name || "").trim().split(/\s+/)[0] || "",
);
const initial = computed(
  () => (ctx.data?.driver?.full_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const tabs = [
  { to: "/", icon: "home", label: "Home" },
  { to: "/attendance", icon: "calendar", label: "Attend" },
  { to: "/trips", icon: "route", label: "Trips" },
  { to: "/fuel", icon: "fuel", label: "Fuel" },
  { to: "/tickets", icon: "help", label: "Support" },
];

// Normalise the payload for the Unlinked screen. On a bootstrap error (rare —
// the API is designed not to 403) we fall back to a safe non-staff shape so the
// user still gets the friendly explainer instead of a blank/crashed page.
const unlinkedCtx = computed(() => {
  const d = ctx.data || {};
  return {
    is_staff: !!d.is_staff,
    full_name: d.full_name || "",
    links: d.links || [],
  };
});
</script>
