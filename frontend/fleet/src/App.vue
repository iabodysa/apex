<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * Fleet EMPLOYEE self-service portal — served at the primary /fleet route.
 *
 * A calm, single-purpose portal (archetype 1 of the approved reference
 * scratch/portal-archetypes-preview.html) built on the shared FleetPageShell
 * (imported by DIRECT path, NOT the @shared/components barrel — the barrel
 * re-exports BuildingPicker, which needs a portal i18n export this portal
 * doesn't provide, so the direct path keeps the fleet bundle clean).
 *
 * This root is a composition surface only: the header (brand · nav · actions)
 * and the per-route heading live here; the content is routed (src/router.js,
 * the worker/driver portals' idiom). Three REAL pages — "/" (my vehicle),
 * "/trips" (my trips) and "/fuel" (fuel request) — replaced the old same-page
 * anchor nav, whose three links scrolled a page that fit one screen, i.e. led
 * nowhere.
 *
 * The old supervisor board that used to live here is preserved untouched at
 * /fleet-os (bundle fleet_os_portal). This page is LIVE — src/useEmployee.js
 * calls the identity-scoped apex.salis.api.fleet_employee endpoints
 * (get_my_vehicle / get_my_recent_trips / get_fuel_stations /
 * submit_fuel_request).
 */
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import FleetPageShell from "@shared/components/FleetPageShell.vue";
import Icon from "./components/Icon.vue";
// [#a281] Direct path, never the "@shared/components" barrel: a name-import from the
// barrel resolves EVERY component it re-exports (incl. any portal-i18n-coupled one)
// in this portal, which is what broke the A-041 builds. See components/index.js.
import LangToggle from "@shared/components/LangToggle.vue";
import ThemeToggle from "@shared/components/ThemeToggle.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { useEmployee } from "./useEmployee.js";

const { t, lang, dir } = useI18n();

useDocumentLanguage(lang, dir);
watch(
  lang,
  () => {
    document.title = t("emp.brand") + " — " + t("emp.brandSub");
  },
  { immediate: true },
);

const route = useRoute();

// Three destinations, all real routes. RouterLink stamps aria-current="page"
// and `is-active` on the exact-active link; the shell styles both.
const navItems = [
  { to: "/", key: "emp.nav.home" },
  { to: "/trips", key: "emp.nav.trips" },
  { to: "/fuel", key: "emp.nav.fuel" },
];

const userName = (typeof window !== "undefined" && window.user_full_name) || "";
const avatarInitial = computed(() => Array.from(userName || t("emp.brand"))[0] || "•");

// Time-of-day greeting.
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("emp.greetMorning");
  if (h < 18) return t("emp.greetAfternoon");
  return t("emp.greetEvening");
});

// One numeral system on screen: `-u-nu-latn` pins the Arabic locale to Latin
// digits, which is what the rest of the product already shows.
const AR_LOCALE = "ar-SA-u-nu-latn";
const todayLabel = computed(() =>
  new Intl.DateTimeFormat(lang.value === "ar" ? AR_LOCALE : "en-US", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date()),
);

// The greeting subtitle keeps its original trip-aware copy: the singleton data
// layer (started here, shared with every page) supplies the preview window.
const { trips } = useEmployee();
const scheduledCount = computed(() => trips.value.filter((x) => x.status !== "completed").length);

// Per-route heading: home keeps the greeting band; the trips and fuel pages
// are titled by their own existing copy.
const pageTitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.title");
  if (route.name === "fuel") return t("emp.fuel.title");
  return greeting.value;
});
const pageSubtitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.hint");
  if (route.name === "fuel") return t("emp.fuel.hint");
  return t("emp.subtitle", { date: todayLabel.value, n: scheduledCount.value });
});
</script>

<template>
  <FleetPageShell :title="pageTitle" :subtitle="pageSubtitle" max-width="1120">
    <template #brand>
      <span class="emp-brandmark"><Icon name="car" :size="19" /></span>
      <span class="emp-brandword">
        {{ t("emp.brand") }}
        <small>{{ t("emp.brandSub") }}</small>
      </span>
    </template>

    <template #nav>
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        active-class=""
        exact-active-class="is-active"
        >{{ t(item.key) }}</router-link
      >
    </template>

    <template #actions>
      <ThemeToggle />
      <!-- variant="header" tints the control for the forest header bar, matching
           the sibling driver / safety / route_supervisor portals. -->
      <LangToggle variant="header" />
      <span class="emp-avatar" :title="userName || t('emp.brand')" :aria-label="userName || t('emp.brand')">{{ avatarInitial }}</span>
    </template>

    <router-view />
  </FleetPageShell>
</template>
