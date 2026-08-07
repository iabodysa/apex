<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="app-shell" :dir="dir">
    <div
      v-if="updateReady"
      class="update-banner flex items-center justify-center gap-2 text-xs font-semibold"
    >
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

    <template v-else-if="worker">
      <MobileConsoleShell :title="workerName" :subtitle="greeting" :max-width="480">
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
    </template>

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
import { computed, watch, ref, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import Icon from "./components/Icon.vue";
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import LangToggle from "./components/LangToggle.vue";
import { useI18n, resourceErrorMessage, setEnumLabels } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { TOKEN, hasToken } from "./utils/token";
import { updateReady, applyUpdate, initPwaUpdates } from "./pwa";
import { usePoll } from "@shared/usePoll.js";

const { t, dir, lang } = useI18n();

const enumLabels = createResource({
  url: "apex.salis.api.masar.get_enum_labels",
  method: "GET",
});

watch(
  lang,
  (l) => {
    if (l === "en") return;
    enumLabels.fetch({ lang: l }, { onSuccess: (data) => setEnumLabels(l, data) });
  },
  { immediate: true },
);

useDocumentLanguage(lang, dir);

const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const syncOnline = () => (online.value = navigator.onLine);
let stopPwaUpdates = null;
onMounted(() => {
  window.addEventListener("online", syncOnline);
  window.addEventListener("offline", syncOnline);
  stopPwaUpdates = initPwaUpdates();
});
onUnmounted(() => {
  window.removeEventListener("online", syncOnline);
  window.removeEventListener("offline", syncOnline);
  if (stopPwaUpdates) stopPwaUpdates();
});

const ctx = createResource({
  url: "apex.salis.api.masar.get_worker_context",
  method: "GET",
  params: { token: TOKEN },
  auto: hasToken,
});

const worker = computed(() => ctx.data && ctx.data.employee && ctx.data);

if (hasToken) usePoll(() => ctx.reload());

const route = useRoute();

const firstName = computed(
  () => (ctx.data?.employee_name || "").trim().split(/\s+/)[0] || "",
);
const workerName = computed(() => (ctx.data?.employee_name || "").trim() || firstName.value);
const initial = computed(
  () => (ctx.data?.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const isTabActive = (tab) =>
  tab.to === "/" ? route.path === "/" : route.path === tab.to || route.path.startsWith(tab.to + "/");

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("greeting.morning");
  if (h < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));

const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
  { to: "/transport", icon: "route", labelKey: "nav.transport" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
];
</script>
