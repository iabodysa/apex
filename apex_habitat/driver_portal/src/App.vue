<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="app-shell" :dir="dir">
    <!-- New build available: a new service worker is installed and waiting. Tap
         reload to activate it; controllerchange then reloads into the new build. -->
    <div v-if="updateReady" class="update-banner">
      <Icon name="refresh" :size="14" class="shrink-0" />
      <span>{{ t("update.available") }}</span>
      <button class="update-reload" @click="applyUpdate">{{ t("update.reload") }}</button>
    </div>

    <!-- Loading -->
    <div v-if="ctx.loading" class="flex-1 grid place-items-center p-8">
      <div class="text-center">
        <div class="spinner mx-auto"></div>
        <p class="mt-3 text-sm text-muted">{{ t("common.loading") }}</p>
      </div>
    </div>

    <!-- Linked driver: branded shell with an icon tab bar. -->
    <template v-else-if="linkedDriver">
      <header class="app-header">
        <!-- Brand supergraphic (decorative, flat, low-contrast) -->
        <div class="hero-arc" aria-hidden="true">
          <Brand mode="arc" />
        </div>

        <div class="header-inner relative z-[1] px-4 pt-4 pb-5">
          <div class="header-bar flex items-center justify-between gap-3">
            <!-- Brand lockup. Tappable home: with only Trips + Profile in the
                 bottom bar, the brand is the one-tap return to the / dashboard. -->
            <router-link
              v-if="showBrand"
              to="/"
              class="flex items-center gap-2 min-w-0"
              :aria-label="t('nav.home')"
              style="text-decoration: none"
            >
              <img
                v-if="brandLogo"
                :src="brandLogo"
                alt="AFMCO"
                class="brand-logo"
              />
              <template v-else>
                <Brand mode="mark" :size="26" />
                <span class="text-lg font-extrabold tracking-tight" style="color: var(--c-header-ink)">
                  AFMCO
                </span>
              </template>
            </router-link>
            <router-link
              v-else
              to="/"
              class="text-lg font-extrabold tracking-tight"
              :aria-label="t('nav.home')"
              style="color: var(--c-header-ink); text-decoration: none"
            >
              Salis
            </router-link>

            <!-- Language selector + driver avatar -->
            <div class="flex items-center gap-2 shrink-0">
              <LangToggle variant="header" />
              <span
                class="avatar h-9 w-9 text-sm"
                style="background: var(--c-header-accent); color: var(--c-header-bg)"
              >
                {{ initial }}
              </span>
            </div>
          </div>

          <!-- Greeting -->
          <div class="greeting-block mt-3">
            <p class="text-xs font-semibold uppercase tracking-wider" style="color: var(--c-header-accent)">
              {{ t("common.driverPortal") }}
            </p>
            <h1 class="text-xl font-extrabold leading-tight truncate" style="color: var(--c-header-ink)">
              {{ greeting }}<span v-if="firstName">, <bdi>{{ firstName }}</bdi></span>
            </h1>
          </div>
        </div>
      </header>

      <main class="flex-1 px-4 pt-5 pb-28 space-y-5">
        <!-- Offline banner: writes are blocked, reads fall back to cached data. -->
        <div v-if="!online" class="offline-banner">
          <Icon name="alert" :size="16" class="shrink-0" />
          <span>{{ t("offline.banner") }}</span>
        </div>
        <!-- First-visit Add-to-Home-Screen hint (self-hides when installed/dismissed). -->
        <InstallHint />
        <router-view :ctx="ctx.data" />
      </main>

      <nav class="tabbar" :style="{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }">
        <router-link v-for="tab in tabs" :key="tab.to" :to="tab.to" class="tab">
          <span class="tab-icon-wrap"><Icon :name="tab.icon" :size="22" /></span>
          <span>{{ t(tab.labelKey) }}</span>
          <span class="tab-pip"></span>
        </router-link>
      </nav>

      <!-- Transient toast host (auto-dismiss + cleared on route change). -->
      <Toast />
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
        <p class="font-bold mb-1">{{ t("errors.loadFailed") }}</p>
        <p class="text-sm text-muted">{{ ctx.error.message || ctx.error }}</p>
        <button class="btn btn-primary mt-4" style="width: auto; padding-inline: 24px" @click="ctx.reload()">
          {{ t("common.retry") }}
        </button>
      </div>
    </div>

    <!-- Everyone else (staff or non-staff): a useful screen, never a dead-end. -->
    <Unlinked v-else :ctx="unlinkedCtx" :show-brand="showBrand" :brand-logo="brandLogo" />
  </div>
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
import Brand from "./components/Brand.vue";
import LangToggle from "./components/LangToggle.vue";
import Toast from "./components/Toast.vue";
import InstallHint from "./components/InstallHint.vue";
import { useI18n } from "./i18n";
import { clearToasts } from "./toast";
import { online } from "./cache";
import { updateReady, applyUpdate, initPwaUpdates } from "./pwa-updates";

const { t, dir } = useI18n();

// Watch the registered service worker for a new build and surface the reload banner.
initPwaUpdates();

// Clear any transient toast when the route changes so a success message never
// lingers onto the next screen.
const route = useRoute();
watch(() => route.fullPath, () => clearToasts());

// Keep the document direction (and lang attribute) in sync with the chosen
// language so native RTL applies to the whole page, scrollbars and inputs
// included — not just the app shell.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// The page template (www/driver.html) sets data-theme server-side, and all theme
// tokens are scoped to [data-theme="…"] (a missing attribute silently falls back to
// the afmco :root defaults, dropping any non-afmco theme like Atelier). Re-assert it
// from the server-projected window.portal_theme only when absent, so the selected
// theme still applies if a different shell (e.g. the built index.html) loads it.
if (!document.documentElement.getAttribute("data-theme") && window.portal_theme) {
  document.documentElement.setAttribute("data-theme", window.portal_theme);
}

// Bootstrap read. method:"GET" is load-bearing: frappe-ui defaults to POST, and
// a POST is CSRF-validated (auth.validate_csrf_token) — so it throws CSRFTokenError
// whenever window.csrf_token is absent/stale at boot (a non-rendered shell, a
// pre-login PWA-cached shell, or a rotated session token). get_driver_context is a
// pure read (identity from the session, no client-supplied scope), so serving it
// over the CSRF-exempt GET path lets the portal always load; writes stay POST+CSRF.
const ctx = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_driver_context",
  method: "GET",
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
  if (h < 12) return t("greeting.morning");
  if (h < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

// Branding flags projected by the page template (www/driver.html). Default to
// showing the brand; an explicit `false` hides it.
const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

// Bottom bar = the two primary jobs only: Trips + Profile. Everything else is
// nested, not demoted to a dead route:
//   - Home (the today/next-trip dashboard) -> the header greeting/brand taps to "/"
//     and Profile > More links it, so the hub is one tap away from either tab.
//   - Route                 -> a Trips card (/route/:trip) and Profile > More (/route)
//   - Vehicle, Attendance   -> Profile > More
//   - Fuel, Support         -> Profile > My Requests
// Two thumb-reachable primaries; every route stays reachable.
const tabs = [
  { to: "/trips", icon: "route", labelKey: "nav.trips" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
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

<style scoped>
/* Header brand logo: a fixed-height box with auto width + object-fit:contain so
   an arbitrarily-shaped uploaded logo keeps its aspect (never stretched), capped
   in width and given a little vertical breathing room inside the header bar. */
.brand-logo {
  display: block;
  height: 28px;
  width: auto;
  max-width: 132px;
  object-fit: contain;
  object-position: left center;
  padding-block: 2px;
  margin-inline-end: 2px;
}
.offline-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg, #fef3c7);
  color: var(--c-warning, #92400e);
}
.update-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--c-accent, #00844e);
  color: #fff;
}
.update-reload {
  font-weight: 700;
  text-decoration: underline;
  padding-inline: 6px;
  color: #fff;
}
</style>
