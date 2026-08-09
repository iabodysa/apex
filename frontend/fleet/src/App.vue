<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <PortalFrame
    :title="pageTitle"
    :eyebrow="pageEyebrow"
    :subtitle="pageSubtitle"
    :navigation-label="t('emp.nav.label')"
    :skip-label="t('common.skipContent')"
  >
    <template #brand>
      <Brand variant="reverse" :size="30" />
      <span class="emp-brandword">
        {{ t("emp.brand") }}
        <small>{{ t("emp.brandSub") }}</small>
      </span>
    </template>

    <template #header-actions>
      <ThemeToggle />
      <LangToggle variant="header" />
      <span
        class="emp-avatar"
        :title="userName || t('emp.brand')"
        :aria-label="userName || t('emp.brand')"
      >{{ avatarInitial }}</span>
    </template>

    <template #nav>
      <span class="fleet-nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          active-class=""
          exact-active-class="is-active"
        >
          <Icon :name="item.icon" :size="18" />
          <span>{{ t(item.key) }}</span>
        </router-link>
      </span>
    </template>

    <router-view v-slot="{ Component }">
      <transition name="emp-scene" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </PortalFrame>

  <PortalToast :toast="toast" />
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";

import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import PortalFrame from "@shared/components/PortalFrame.vue";
import ThemeToggle from "@shared/components/ThemeToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";

import Icon from "./Icon.vue";
import PortalToast from "./components/PortalToast.vue";
import { formatToday } from "./fmt.js";
import { provideToast } from "./toast.js";
import { useI18n } from "@/i18n";

const { t, lang, dir } = useI18n();
useDocumentLanguage(lang, dir);

watch(
  lang,
  () => {
    document.title = t("emp.brand") + " — " + t("emp.brandSub");
  },
  { immediate: true },
);

const { toast } = provideToast();
const route = useRoute();

const navItems = [
  { to: "/", key: "emp.nav.home", icon: "home" },
  { to: "/trips", key: "emp.nav.trips", icon: "clipboard-list" },
  { to: "/fuel", key: "emp.nav.fuel", icon: "fuel" },
];

const userName = (typeof window !== "undefined" && window.user_full_name) || "";
const avatarInitial = computed(() => Array.from(userName || t("emp.brand"))[0] || "•");

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return t("emp.greetMorning");
  if (hour < 18) return t("emp.greetAfternoon");
  return t("emp.greetEvening");
});

const pageTitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.title");
  if (route.name === "fuel") return t("emp.fuel.title");
  return greeting.value;
});

const pageEyebrow = computed(() =>
  route.name === "home" ? formatToday(lang.value) : t("emp.brandSub"),
);

const pageSubtitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.windowHint");
  if (route.name === "fuel") return t("emp.fuel.hint");
  return t("emp.today.subtitle");
});
</script>
