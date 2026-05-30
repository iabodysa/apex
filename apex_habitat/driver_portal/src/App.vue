<template>
  <div class="app-shell">
    <!-- Loading -->
    <div v-if="ctx.loading" class="flex-1 grid place-items-center p-8">
      <div class="text-center">
        <div class="spinner mx-auto"></div>
        <p class="mt-3 text-sm text-muted">Loading…</p>
      </div>
    </div>

    <!-- Linked driver: branded shell with an icon tab bar. -->
    <template v-else-if="linkedDriver">
      <header class="app-header">
        <!-- Brand supergraphic (decorative, flat, low-contrast) -->
        <div class="hero-arc" aria-hidden="true">
          <Brand mode="arc" />
        </div>

        <div class="relative z-[1] px-4 pt-4 pb-5">
          <div class="flex items-center justify-between gap-3">
            <!-- Brand lockup -->
            <div v-if="showBrand" class="flex items-center gap-2 min-w-0">
              <img
                v-if="brandLogo"
                :src="brandLogo"
                alt="AFMCO"
                class="h-7 w-auto max-w-[120px] object-contain"
              />
              <template v-else>
                <Brand mode="mark" :size="26" />
                <span class="text-lg font-extrabold tracking-tight" style="color: var(--c-header-ink)">
                  AFMCO
                </span>
              </template>
            </div>
            <span
              v-else
              class="text-lg font-extrabold tracking-tight"
              style="color: var(--c-header-ink)"
            >
              Salis
            </span>

            <!-- Driver avatar -->
            <span
              class="avatar h-9 w-9 text-sm"
              style="background: var(--c-header-accent); color: var(--c-header-bg)"
            >
              {{ initial }}
            </span>
          </div>

          <!-- Greeting -->
          <div class="mt-3">
            <p class="text-xs font-semibold uppercase tracking-wider" style="color: var(--c-header-accent)">
              Driver Portal
            </p>
            <h1 class="text-xl font-extrabold leading-tight truncate" style="color: var(--c-header-ink)">
              {{ greeting }}<span v-if="firstName">, {{ firstName }}</span>
            </h1>
          </div>
        </div>
      </header>

      <main class="flex-1 px-4 pt-5 pb-28">
        <router-view :ctx="ctx.data" />
      </main>

      <nav class="tabbar">
        <router-link v-for="t in tabs" :key="t.to" :to="t.to" class="tab">
          <span class="tab-icon-wrap"><Icon :name="t.icon" :size="22" /></span>
          <span>{{ t.label }}</span>
          <span class="tab-pip"></span>
        </router-link>
      </nav>
    </template>

    <!-- A genuine server error: surface it. Never mis-render as "not linked". -->
    <div v-else-if="ctx.error" class="flex-1 grid place-items-center p-8 text-center">
      <div>
        <div
          class="avatar mx-auto mb-3 h-12 w-12"
          style="background: var(--c-danger-bg); color: var(--c-danger)"
        >
          <Icon name="alert" :size="26" />
        </div>
        <p class="font-bold mb-1">Couldn't load the portal</p>
        <p class="text-sm text-muted">{{ ctx.error.message || ctx.error }}</p>
        <button class="btn btn-primary mt-4" style="width: auto; padding-inline: 24px" @click="ctx.reload()">
          Retry
        </button>
      </div>
    </div>

    <!-- Everyone else (staff or non-staff): a useful screen, never a dead-end. -->
    <Unlinked v-else :ctx="unlinkedCtx" :show-brand="showBrand" :brand-logo="brandLogo" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
import Brand from "./components/Brand.vue";

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

// Time-of-day greeting (purely cosmetic).
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
});

// Branding flags projected by the page template (www/driver.html). Default to
// showing the brand; an explicit `false` hides it.
const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

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
