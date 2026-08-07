<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import FleetPageShell from "@shared/components/FleetPageShell.vue";
import Icon from "./components/Icon.vue";
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

const AR_LOCALE = "ar-SA-u-nu-latn";
const todayLabel = computed(() =>
  new Intl.DateTimeFormat(lang.value === "ar" ? AR_LOCALE : "en-US", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date()),
);

const { trips } = useEmployee();
const scheduledCount = computed(() => trips.value.filter((x) => x.status !== "completed").length);

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
      <LangToggle variant="header" />
      <span class="emp-avatar" :title="userName || t('emp.brand')" :aria-label="userName || t('emp.brand')">{{ avatarInitial }}</span>
    </template>

    <router-view />
  </FleetPageShell>
</template>
