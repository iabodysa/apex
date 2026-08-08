<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="app-shell" :dir="dir">
    <div v-if="updateReady" class="update-banner flex items-center justify-center gap-2 text-xs font-semibold">
      <Icon name="refresh" :size="14" />
      <span>{{ t("update.available") }}</span>
      <button class="update-reload font-bold underline" @click="applyUpdate">
        {{ t("update.reload") }}
      </button>
    </div>

    <div
      v-if="!online"
      class="flex items-center justify-center gap-2 text-xs font-semibold"
      style="background: var(--c-warning-bg); color: var(--c-warning); padding: 6px 12px"
    >
      <Icon name="alert" :size="14" />
      <span>{{ t("common.offline") }}</span>
    </div>

    <div v-if="!hasToken" class="flex-1 grid place-items-center p-8 text-center">
      <div>
        <div class="avatar mx-auto mb-3 h-12 w-12" style="background: var(--c-warning-bg); color: var(--c-warning)">
          <Icon name="alert" :size="26" />
        </div>
        <p class="font-bold mb-1">{{ t("errors.loadFailed") }}</p>
        <p class="text-sm text-muted">{{ t("errors.noLink") }}</p>
        <div class="mt-4 flex justify-center"><LangToggle /></div>
      </div>
    </div>

    <div v-else-if="ctx.loading && !worker" class="flex-1 grid place-items-center p-8">
      <div class="text-center">
        <div class="spinner mx-auto"></div>
        <p class="mt-3 text-sm text-muted">{{ t("common.loading") }}</p>
      </div>
    </div>

    <MobileConsoleShell v-else-if="worker" :title="workerName" :subtitle="greeting" :max-width="480">
      <template #header-actions>
        <LangToggle variant="header" />
        <span
          class="avatar h-9 w-9 text-sm overflow-hidden"
          style="background: var(--c-header-accent); color: var(--c-header-bg)"
        >
          <img v-if="worker.photo" :src="worker.photo" alt="" class="h-full w-full object-cover" />
          <template v-else>{{ initial }}</template>
        </span>
      </template>

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
          <Icon :name="tab.icon" :size="22" :class="{ 'rtl-flip': tab.icon === 'route' }" />
          <span>{{ t(tab.labelKey) }}</span>
        </router-link>
      </template>
    </MobileConsoleShell>

    <div v-else class="flex-1 grid place-items-center p-8 text-center">
      <div>
        <div class="avatar mx-auto mb-3 h-12 w-12" style="background: var(--c-danger-bg); color: var(--c-danger)">
          <Icon name="alert" :size="26" />
        </div>
        <p class="font-bold mb-1">{{ t("errors.loadFailed") }}</p>
        <p class="text-sm text-muted">{{ errorMessage }}</p>
        <button class="btn btn-primary mt-4" style="width: auto; padding-inline: 24px" @click="ctx.reload()">
          {{ t("common.retry") }}
        </button>
        <div class="mt-4 flex justify-center"><LangToggle /></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
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
const initial = computed(
  () => (ctx.data?.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const isTabActive = (tab) =>
  tab.to === "/" ? route.path === "/" : route.path === tab.to || route.path.startsWith(tab.to + "/");

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return t("greeting.morning");
  if (hour < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));

const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
  { to: "/transport", icon: "route", labelKey: "nav.transport" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
];
</script>
