<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="app-shell" :dir="dir">
    <MobileConsoleShell
      v-if="ctx.loading"
      :title="t('common.driverPortal')"
      :subtitle="fmtTodayDate()"
      :max-width="480"
    >
      <TodaySkeleton :label="t('common.loading')" />
    </MobileConsoleShell>

    <template v-else-if="linkedDriver">
      <MobileConsoleShell :title="driverName" :subtitle="fmtTodayDate()" :max-width="480">
        <template #header-actions>
          <LangToggle variant="header" />
          <span
            class="avatar h-9 w-9 text-sm"
            style="background: var(--c-header-accent); color: var(--c-header-bg)"
          >
            {{ initial }}
          </span>
        </template>

        <div v-if="!online" class="offline-banner">
          <Icon name="alert" :size="16" class="shrink-0" />
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
          >
            <Icon :name="tab.icon" :size="22" />
            <span>{{ t(tab.labelKey) }}</span>
          </router-link>
        </template>
      </MobileConsoleShell>

      <Toast />
    </template>

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

    <Unlinked v-else :ctx="unlinkedCtx" :show-brand="showBrand" :brand-logo="brandLogo" />
  </div>
</template>

<script setup>
import { computed, watch, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import Unlinked from "./components/Unlinked.vue";
import Icon from "./components/Icon.vue";
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

const firstName = computed(
  () => (ctx.data?.driver?.full_name || "").trim().split(/\s+/)[0] || "",
);
const driverName = computed(() => (ctx.data?.driver?.full_name || "").trim() || firstName.value);
const initial = computed(
  () => (ctx.data?.driver?.full_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const isTabActive = (tab) =>
  tab.to === "/" ? route.path === "/" : route.path === tab.to || route.path.startsWith(tab.to + "/");

const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
  { to: "/trips", icon: "route", labelKey: "nav.trips" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
];

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
</style>
