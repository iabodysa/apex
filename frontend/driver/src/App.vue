<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="app-shell" :dir="dir">
    <PortalFrame
      v-if="linkedDriver"
      :title="scene.title"
      :eyebrow="fmtTodayDate()"
      :subtitle="driverName"
      :navigation-label="t('common.driverPortal')"
      :skip-label="t('common.skipContent')"
    >
      <template #header-actions>
        <LangToggle variant="header" />
        <span class="identity-chip" :aria-label="driverName">{{ initial }}</span>
      </template>

      <div v-if="!online" class="system-banner system-banner-offline" role="status">
        <Icon name="alert" :size="16" />
        <span>{{ t("offline.banner") }}</span>
      </div>
      <InstallHint />
      <router-view :ctx="ctx.data" />

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
    </PortalFrame>

    <PortalFrame
      v-else-if="ctx.loading || ctx.error"
      :title="t('common.driverPortal')"
      :eyebrow="fmtTodayDate()"
      :subtitle="ctx.loading ? t('common.loading') : errorMessage"
      :skip-label="t('common.skipContent')"
    >
      <template #header-actions><LangToggle variant="header" /></template>
      <AsyncBoundary
        :state="ctx.loading ? 'loading' : 'error'"
        :title="ctx.loading ? '' : t('errors.loadFailed')"
        :message="ctx.loading ? '' : errorMessage"
        :retry-label="ctx.error ? t('common.retry') : ''"
        @retry="ctx.reload()"
      />
    </PortalFrame>

    <Unlinked v-else :ctx="unlinkedCtx" :show-brand="showBrand" :brand-logo="brandLogo" />
    <Toast />
  </div>
</template>

<script setup>
import { computed, watch, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import PortalFrame from "@shared/components/PortalFrame.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
import Toast from "./components/Toast.vue";
import InstallHint from "./components/InstallHint.vue";
import { useI18n, resourceErrorMessage } from "./i18n";
import { clearToasts } from "./toast";
import { online } from "./cache";
import { driverContext } from "./session.js";
import { initPwaUpdates } from "./pwa-updates";

const { t, lang, dir, fmtTodayDate } = useI18n();
const stopPwaUpdates = initPwaUpdates();
onUnmounted(() => stopPwaUpdates && stopPwaUpdates());

const route = useRoute();
watch(() => route.fullPath, () => clearToasts());
useDocumentLanguage(lang, dir);

if (!document.documentElement.getAttribute("data-theme") && window.portal_theme) {
  document.documentElement.setAttribute("data-theme", window.portal_theme);
}

const ctx = driverContext();
const linkedDriver = computed(
  () => ctx.data && ctx.data.enabled && ctx.data.linked && ctx.data.driver,
);
const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));
const driverName = computed(() => (ctx.data?.driver?.full_name || "").trim());
const initial = computed(() => driverName.value.charAt(0).toUpperCase() || "?");

const scene = computed(() => {
  const name = route.name;
  if (name === "attendance") return { title: t("attendance.title") };
  if (name === "trips") return { title: t("trips.title") };
  if (name === "route" || name === "trip-route") return { title: t("route.tripTitle") };
  if (name === "fuel") return { title: t("fuel.title") };
  if (name === "tickets") return { title: t("tickets.title") };
  if (name === "vehicle") return { title: t("vehicle.title") };
  if (name === "profile") return { title: t("profile.more") };
  return { title: t("home.today") };
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

const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");
const unlinkedCtx = computed(() => {
  const d = ctx.data || {};
  return {
    is_staff: !!d.is_staff,
    full_name: d.full_name || "",
    links: d.links || [],
  };
});
</script>
