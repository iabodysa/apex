<!-- Copyright (c) 2026, afmcoltd -->
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
      <LangToggle variant="header" />
      <span
        class="emp-avatar"
        :title="userName || t('emp.brand')"
        :aria-label="userName || t('emp.brand')"
        >{{ avatarInitial }}</span
      >
    </template>

    <router-view />
  </FleetPageShell>

  <PortalToast :toast="toast" />
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";

import FleetPageShell from "@shared/components/FleetPageShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import ThemeToggle from "@shared/components/ThemeToggle.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";

import Icon from "./Icon.vue";
import PortalToast from "./components/PortalToast.vue";
import { formatToday } from "./fmt.js";
import { provideToast } from "./toast.js";
import { useEmployee } from "./useEmployee.js";
import { useI18n } from "@/i18n";

const { t, lang, dir } = useI18n();
useDocumentLanguage(lang, dir);

/* The tab title follows the interface language, not the render language: the page is served in
   Arabic but the reader may have switched. */
watch(
  lang,
  () => {
    document.title = t("emp.brand") + " — " + t("emp.brandSub");
  },
  { immediate: true },
);

const { toast } = provideToast();
const route = useRoute();
const { trips } = useEmployee();

const navItems = [
  { to: "/", key: "emp.nav.home" },
  { to: "/trips", key: "emp.nav.trips" },
  { to: "/fuel", key: "emp.nav.fuel" },
];

const userName = (typeof window !== "undefined" && window.user_full_name) || "";
const avatarInitial = computed(() => Array.from(userName || t("emp.brand"))[0] || "•");

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("emp.greetMorning");
  if (h < 18) return t("emp.greetAfternoon");
  return t("emp.greetEvening");
});

const openTrips = computed(() => trips.state.data.filter((x) => x.status !== "completed").length);

const pageTitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.title");
  if (route.name === "fuel") return t("emp.fuel.title");
  return greeting.value;
});
const pageSubtitle = computed(() => {
  if (route.name === "trips") return t("emp.trips.hint");
  if (route.name === "fuel") return t("emp.fuel.hint");
  return t("emp.subtitle", { date: formatToday(lang.value), n: openTrips.value });
});
</script>
