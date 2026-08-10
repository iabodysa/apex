<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="app-shell" :dir="dir">
    <a class="portal-skip" href="#portal-detail">{{ t("common.skipContent") }}</a>

    <div v-if="updateReady" class="system-banner system-banner-update" role="status">
      <Icon name="refresh" :size="16" />
      <span>{{ t("update.available") }}</span>
      <Button variant="ghost" size="md" :label="t('update.reload')" @click="applyUpdate" />
    </div>

    <MobileConsoleShell
      v-if="hasToken && worker"
    >
      <template #header>
        <div class="masar-head-row">
          <Brand variant="reverse" :size="34" />
          <div class="masar-head-copy">
            <small>{{ t("common.workerApp") }} · {{ greeting }}</small>
            <h1 class="masar-title">{{ scene.title }}</h1>
          </div>
          <div class="masar-head-actions">
            <LangToggle variant="header" />
            <span class="identity-chip" :aria-label="workerName">
              <img v-if="worker.photo" :src="worker.photo" alt="" />
              <span v-else>{{ initial }}</span>
            </span>
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
          <Icon :name="tab.icon" :size="21" :class="{ 'rtl-flip': tab.icon === 'route' }" />
          <span>{{ t(tab.labelKey) }}</span>
        </router-link>
      </template>

      <template v-if="scene.links.length" #list>
        <section class="masar-context-list" :aria-label="scene.title">
          <p>{{ t("common.workerApp") }}</p>
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
          <span>{{ t("common.offline") }}</span>
        </div>
        <router-view :ctx="ctx.data" />
      </section>

      <template v-if="scene.action" #action>
        <Button
          variant="solid"
          theme="green"
          size="2xl"
          :label="scene.action.label"
          :route="scene.action.to"
        >
          <template #prefix><Icon :name="scene.action.icon" :size="20" /></template>
        </Button>
      </template>
    </MobileConsoleShell>

    <MobileConsoleShell v-else>
      <template #header>
        <div class="masar-head-row">
          <Brand variant="reverse" :size="34" />
          <div class="masar-head-copy">
            <small>{{ greeting }}</small>
            <h1 class="masar-title">{{ t("common.workerApp") }}</h1>
          </div>
          <div class="masar-head-actions"><LangToggle variant="header" /></div>
        </div>
      </template>

      <section id="portal-detail" class="masar-detail" tabindex="-1">
        <AsyncBoundary
          :state="accessState"
          :title="accessTitle"
          :message="accessMessage"
          :retry-label="accessState === 'error' ? t('common.retry') : ''"
          @retry="ctx.reload()"
        />
      </section>
    </MobileConsoleShell>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { Button, createResource } from "frappe-ui";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import Brand from "@shared/components/Brand.vue";
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { usePoll } from "@shared/usePoll.js";
import Icon from "./components/Icon.vue";
import LangToggle from "./components/LangToggle.vue";
import { useI18n, resourceErrorMessage, setEnumLabels } from "./i18n";
import { hasToken } from "./token.js";
import { online } from "./storage.js";
import { workerContext } from "./session.js";
import { updateReady, applyUpdate, initPwaUpdates } from "./pwa";

const { t, dir, lang } = useI18n();
useDocumentLanguage(lang, dir);

const enumLabels = createResource({
  url: "apex.salis.api.masar.get_enum_labels",
  method: "GET",
});

watch(
  lang,
  (code) => {
    if (code === "en") return;
    enumLabels.fetch({ lang: code }, { onSuccess: (data) => setEnumLabels(code, data) });
  },
  { immediate: true },
);

let stopPwaUpdates = null;
onMounted(() => {
  stopPwaUpdates = initPwaUpdates();
});
onUnmounted(() => {
  if (stopPwaUpdates) stopPwaUpdates();
});

const ctx = workerContext();
const worker = computed(() => ctx.data && ctx.data.employee && ctx.data);
if (hasToken) usePoll(() => ctx.reload());

const route = useRoute();
const workerName = computed(() => (ctx.data?.employee_name || "").trim());
const initial = computed(() => workerName.value.charAt(0).toUpperCase() || "?");

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return t("greeting.morning");
  if (hour < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

const scene = computed(() => {
  const name = route.name;
  const transportLinks = [
    { to: "/transport", icon: "route", label: t("nav.transport"), routes: ["transport"] },
    {
      to: "/request-transport",
      icon: "plus",
      label: t("reqTransport.title"),
      routes: ["request-transport"],
    },
  ];
  const housingLinks = [
    {
      to: "/accommodation",
      icon: "building",
      label: t("nav.accommodation"),
      routes: ["accommodation"],
    },
    { to: "/custody", icon: "briefcase", label: t("nav.custody"), routes: ["custody"] },
    {
      to: "/requests",
      icon: "help",
      label: t("nav.requests"),
      routes: ["requests", "request-detail"],
    },
  ];

  if (name === "transport") {
    return {
      title: t("transport.title"),
      links: transportLinks,
      action: { to: "/request-transport", icon: "plus", label: t("reqTransport.title") },
    };
  }
  if (name === "request-transport") {
    return { title: t("reqTransport.title"), links: transportLinks };
  }
  if (name === "accommodation") {
    return {
      title: t("accommodation.title"),
      links: housingLinks,
      action: { to: "/requests", icon: "plus", label: t("requests.new") },
    };
  }
  if (name === "custody") return { title: t("custody.title"), links: housingLinks };
  if (name === "requests") return { title: t("requests.title"), links: housingLinks };
  if (name === "request-detail") {
    return { title: t("requests.detailTitle"), links: housingLinks };
  }
  if (name === "profile") return { title: t("profile.title"), links: [] };
  return { title: t("home.title"), links: [] };
});

const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home", routes: ["home"] },
  {
    to: "/transport",
    icon: "route",
    labelKey: "nav.transport",
    routes: ["transport", "request-transport"],
  },
  {
    to: "/accommodation",
    icon: "building",
    labelKey: "nav.housingHelp",
    routes: ["accommodation", "custody", "requests", "request-detail"],
  },
  { to: "/profile", icon: "user", labelKey: "nav.profile", routes: ["profile"] },
];

const isTabActive = (tab) => tab.routes.includes(route.name);
const isSceneLinkActive = (link) => link.routes.includes(route.name);

const accessState = computed(() => {
  if (!hasToken) return "empty";
  if (ctx.loading) return "loading";
  return ctx.error ? "error" : "empty";
});
const accessTitle = computed(() =>
  accessState.value === "loading" ? "" : t("errors.loadFailed"),
);
const accessMessage = computed(() => {
  if (!hasToken) return t("errors.noLink");
  if (ctx.error) return resourceErrorMessage(ctx.error, "errors.invalidLink");
  return t("errors.invalidLink");
});
</script>
