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

    <MobileConsoleShell
      v-if="ctx.loading"
      :title="t('common.driverPortal')"
      :subtitle="fmtTodayDate()"
      :max-width="480"
    >
      <TodaySkeleton :label="t('common.loading')" />
    </MobileConsoleShell>

    <!-- Linked driver: shared Mobile-console archetype (sticky dark header,
         single scrolling card column, sticky ≥52px bottom nav). -->
    <template v-else-if="linkedDriver">
      <MobileConsoleShell :title="driverName" :subtitle="fmtTodayDate()" :max-width="480">
        <!-- Header end: language toggle + driver avatar -->
        <template #header-actions>
          <LangToggle variant="header" />
          <span
            class="avatar h-9 w-9 text-sm"
            style="background: var(--c-header-accent); color: var(--c-header-bg)"
          >
            {{ initial }}
          </span>
        </template>

        <!-- Scroll column: offline notice + install hint + the routed page. -->
        <!-- Offline banner: writes are blocked, reads fall back to cached data. -->
        <div v-if="!online" class="offline-banner">
          <Icon name="alert" :size="16" class="shrink-0" />
          <span>{{ t("offline.banner") }}</span>
        </div>
        <!-- First-visit Add-to-Home-Screen hint (self-hides when installed/dismissed). -->
        <InstallHint />
        <router-view :ctx="ctx.data" />

        <!-- Bottom nav (3 primary destinations). The Home tab ("/") is a prefix
             of every route, so its inclusive match would light up everywhere;
             isTabActive() keeps Home exact and the others inclusive. The shell
             tints the `.is-active` child with the brand. -->
        <template #nav>
          <router-link
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            :class="{ 'is-active': isTabActive(tab) }"
            active-class=""
            exact-active-class=""
          >
            <Icon :name="tab.icon" :size="22" />
            <span>{{ t(tab.labelKey) }}</span>
          </router-link>
        </template>
      </MobileConsoleShell>

      <!-- Transient toast host (auto-dismiss + cleared on route change). -->
      <Toast />
    </template>

    <!-- A genuine server error: surface it. Never mis-render as "not linked". -->
    <MobileConsoleShell
      v-else-if="ctx.error"
      :title="t('common.driverPortal')"
      :subtitle="fmtTodayDate()"
      :max-width="480"
    >
      <LoadError
        :title="t('errors.loadFailed')"
        :detail="errorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="ctx.reload()"
      />
    </MobileConsoleShell>

    <!-- Everyone else (staff or non-staff): a useful screen, never a dead-end. -->
    <Unlinked v-else :ctx="unlinkedCtx" :show-brand="showBrand" :brand-logo="brandLogo" />
  </div>
</template>

<script setup>
import { computed, watch, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
// Direct-path (not the barrel): the @shared/components barrel re-exports
// BuildingPicker, which imports resourceErrorMessage from the portal i18n — a
// symbol the driver i18n doesn't export, so the barrel would break this build.
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import Toast from "./components/Toast.vue";
import InstallHint from "./components/InstallHint.vue";
import TodaySkeleton from "./components/TodaySkeleton.vue";
import LoadError from "@shared/components/LoadError.vue";
import { useI18n, resourceErrorMessage } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { clearToasts } from "./toast";
import { online } from "./cache";
import { updateReady, applyUpdate, initPwaUpdates } from "./pwa-updates";

const { t, lang, dir, fmtTodayDate } = useI18n();

// Watch the registered service worker for a new build and surface the reload
// banner. Tear it down on unmount so its interval/listeners don't stack on an
// HMR re-init of the App root.
const stopPwaUpdates = initPwaUpdates();
onUnmounted(() => stopPwaUpdates && stopPwaUpdates());

// Clear any transient toast when the route changes so a success message never
// lingers onto the next screen.
const route = useRoute();
watch(() => route.fullPath, () => clearToasts());

useDocumentLanguage(lang, dir);

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
  url: "apex.salis.api.driver_portal.get_driver_context",
  method: "GET",
  auto: true,
});

const linkedDriver = computed(
  () => ctx.data && ctx.data.enabled && ctx.data.linked && ctx.data.driver,
);

// The bootstrap error was rendered raw, so a refused token put the request path and
// the Python exception class on a driver's phone. Same treatment as the /masar shell:
// map the failure to a short line in the language the driver actually picked — a real
// refusal reads as "bad or disabled link", a transient one stays retry-able.
const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));

const firstName = computed(
  () => (ctx.data?.driver?.full_name || "").trim().split(/\s+/)[0] || "",
);
// Header title = the driver's name; the greeting is the small line above it.
const driverName = computed(() => (ctx.data?.driver?.full_name || "").trim() || firstName.value);
const initial = computed(
  () => (ctx.data?.driver?.full_name || "?").trim().charAt(0).toUpperCase() || "?",
);

// Bottom-nav highlight: Home ("/") only on the exact root; every other tab is
// active for its whole subtree (e.g. Trips stays lit on /trips/:id).
const isTabActive = (tab) =>
  tab.to === "/" ? route.path === "/" : route.path === tab.to || route.path.startsWith(tab.to + "/");

// Branding flags projected by the page template (www/driver.html). Default to
// showing the brand; an explicit `false` hides it.
const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

// Bottom bar = the three primary destinations: Home + Trips + Profile. The brand
// also taps to "/", but Home is a first-class tab so the dashboard is never hidden.
// Secondary routes stay nested, not demoted to a dead route:
//   - Route                 -> a Trips card (/route/:trip) and Profile > More (/route)
//   - Vehicle, Attendance   -> Profile > More
//   - Fuel, Support         -> Profile > My Requests
const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
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
   an arbitrarily-shaped uploaded logo keeps its aspect (never stretched). It is
   capped in width and wrapped in clear breathing room so it never reads as
   cramped/edge-to-edge: flex-shrink:0 stops the flex row from squeezing it (a
   squeezed fixed-aspect logo looks distorted), and the block/inline padding give
   it visible spacing inside the header bar. */
.brand-logo {
  display: block;
  flex-shrink: 0;
  height: 28px;
  width: auto;
  max-width: 132px;
  object-fit: contain;
  object-position: left center;
  padding-block: 4px;
  margin-inline-end: 8px;
}
.offline-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.update-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--c-accent);
  color: var(--c-primary-ink);
}
/* --tap-min: the accessible floor. It was inline text with 6px of side padding,
   which no thumb reliably hits. */
.update-reload {
  display: inline-flex;
  align-items: center;
  min-height: var(--tap-min);
  font-weight: 700;
  text-decoration: underline;
  padding-inline: 10px;
  color: var(--c-primary-ink);
}
</style>
