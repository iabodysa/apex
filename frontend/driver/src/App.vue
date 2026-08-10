<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <FrappeUIProvider>
    <div class="app-shell" :dir="dir">
      <a class="portal-skip" href="#portal-detail">{{ t("common.skipContent") }}</a>

      <MobileConsoleShell
        v-if="linkedDriver"
      >
        <template #header>
          <div class="masar-head-row">
            <Brand variant="reverse" :size="34" />
            <div class="masar-head-copy">
              <small>{{ t("common.driverPortal") }} · <bdi>{{ fmtTodayDate() }}</bdi></small>
              <b>{{ scene.title }}</b>
            </div>
            <div class="masar-head-actions">
              <LangToggle variant="header" />
              <span class="identity-chip" :aria-label="driverName">{{ initial }}</span>
            </div>
          </div>
        </template>

        <template #nav>
          <router-link
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            :class="{ 'is-active': isTabActive(tab) }"
            active-class=""
            exact-active-class=""
            :aria-current="isTabActive(tab) ? 'page' : undefined"
          >
            <Icon :name="tab.icon" :size="21" />
            <span>{{ t(tab.labelKey) }}</span>
          </router-link>
        </template>

        <template v-if="scene.links.length" #list>
          <section class="masar-context-list" :aria-label="scene.title">
            <p>{{ t("common.driverPortal") }}</p>
            <h2>{{ scene.title }}</h2>
            <router-link
              v-for="link in scene.links"
              :key="link.to"
              :to="link.to"
              :class="{ 'is-active': isSceneLinkActive(link) }"
              :aria-current="isSceneLinkActive(link) ? 'page' : undefined"
            >
              <Icon :name="link.icon" :size="20" />
              <span>{{ link.label }}</span>
            </router-link>
          </section>
        </template>

        <section id="portal-detail" class="masar-detail" tabindex="-1">
          <div v-if="!online" class="system-banner system-banner-offline" role="status">
            <Icon name="alert" :size="16" />
            <span>{{ t("offline.banner") }}</span>
          </div>
          <router-view :ctx="ctx.data" />
        </section>

        <template v-if="showInstallHint" #action><InstallHint /></template>
      </MobileConsoleShell>

      <MobileConsoleShell v-else>
        <template #header>
          <div class="masar-head-row">
            <Brand variant="reverse" :size="34" />
            <div class="masar-head-copy">
              <small><bdi>{{ fmtTodayDate() }}</bdi></small>
              <b>{{ t("common.driverPortal") }}</b>
            </div>
            <div class="masar-head-actions"><LangToggle variant="header" /></div>
          </div>
        </template>

        <section id="portal-detail" class="masar-detail" tabindex="-1">
          <AsyncBoundary
            v-if="ctx.loading || ctx.error"
            :state="ctx.loading ? 'loading' : 'error'"
            :title="ctx.loading ? '' : t('errors.loadFailed')"
            :message="ctx.loading ? '' : errorMessage"
            :retry-label="ctx.error ? t('common.retry') : ''"
            @retry="ctx.reload()"
          />
          <Unlinked v-else :ctx="unlinkedCtx" />
        </section>
      </MobileConsoleShell>
    </div>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, watch, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { FrappeUIProvider } from "frappe-ui";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import Brand from "@shared/components/Brand.vue";
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
import InstallHint from "./components/InstallHint.vue";
import { useI18n, resourceErrorMessage } from "./i18n";
import { clearToasts } from "./toast";
import { online } from "./cache";
import { driverContext } from "./session.js";
import { initPwaUpdates } from "./pwa-updates";
import { showInstallHint } from "./pwa";

const { t, lang, dir, fmtTodayDate } = useI18n();
const stopPwaUpdates = initPwaUpdates();
onUnmounted(() => stopPwaUpdates && stopPwaUpdates());

const route = useRoute();
watch(() => route.fullPath, () => clearToasts());
useDocumentLanguage(lang, dir);

const ctx = driverContext();
const linkedDriver = computed(
  () => ctx.data && ctx.data.enabled && ctx.data.linked && ctx.data.driver,
);
const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));
const driverName = computed(() => (ctx.data?.driver?.full_name || "").trim());
const initial = computed(() => driverName.value.charAt(0).toUpperCase() || "?");

const scene = computed(() => {
  const name = route.name;
  const homeLinks = [
    { to: "/", icon: "home", label: t("nav.home"), routes: ["home"] },
    {
      to: "/attendance",
      icon: "calendar",
      label: t("nav.attendance"),
      routes: ["attendance"],
    },
  ];
  const tripLinks = [
    { to: "/trips", icon: "route", label: t("nav.trips"), routes: ["trips"] },
    {
      to: "/route",
      icon: "map-pin",
      label: t("nav.route"),
      routes: ["route", "trip-route"],
    },
  ];
  const profileLinks = [
    { to: "/profile", icon: "user", label: t("nav.profile"), routes: ["profile"] },
    { to: "/vehicle", icon: "truck", label: t("nav.vehicle"), routes: ["vehicle"] },
    { to: "/fuel", icon: "fuel", label: t("nav.fuel"), routes: ["fuel"] },
    { to: "/tickets", icon: "help", label: t("nav.tickets"), routes: ["tickets"] },
  ];

  if (name === "attendance") return { title: t("attendance.title"), links: homeLinks };
  if (name === "trips") return { title: t("trips.title"), links: tripLinks };
  if (name === "route" || name === "trip-route") {
    return { title: t("route.tripTitle"), links: tripLinks };
  }
  if (name === "fuel") return { title: t("fuel.title"), links: profileLinks };
  if (name === "tickets") return { title: t("tickets.title"), links: profileLinks };
  if (name === "vehicle") return { title: t("vehicle.title"), links: profileLinks };
  if (name === "profile") return { title: t("profile.more"), links: profileLinks };
  return { title: t("home.today"), links: homeLinks };
});

const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home", routes: ["home", "attendance"] },
  {
    to: "/trips",
    icon: "route",
    labelKey: "nav.trips",
    routes: ["trips", "route", "trip-route"],
  },
  {
    to: "/profile",
    icon: "user",
    labelKey: "nav.more",
    routes: ["profile", "vehicle", "fuel", "tickets"],
  },
];
const isTabActive = (tab) => tab.routes.includes(route.name);
const isSceneLinkActive = (link) => link.routes.includes(route.name);
const unlinkedCtx = computed(() => {
  const d = ctx.data || {};
  return {
    is_staff: !!d.is_staff,
    full_name: d.full_name || "",
    links: d.links || [],
  };
});
</script>
