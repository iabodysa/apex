<template>
  <div class="app-shell" :dir="dir">
    <!-- No token at all: the link is incomplete. -->
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

    <!-- Loading -->
    <div v-else-if="ctx.loading" class="flex-1 grid place-items-center p-8">
      <div class="text-center">
        <div class="spinner mx-auto"></div>
        <p class="mt-3 text-sm text-muted">{{ t("common.loading") }}</p>
      </div>
    </div>

    <!-- Resolved worker: branded shell + bottom tab bar. -->
    <template v-else-if="worker">
      <header class="app-header">
        <div class="hero-arc" aria-hidden="true"><Brand mode="arc" /></div>
        <div class="header-inner relative z-[1] px-4 pt-4 pb-5">
          <div class="header-bar flex items-center justify-between gap-3">
            <div v-if="showBrand" class="flex items-center gap-2 min-w-0">
              <img v-if="brandLogo" :src="brandLogo" alt="AFMCO" class="h-7 w-auto max-w-[120px] object-contain" />
              <template v-else>
                <Brand mode="mark" :size="26" />
                <span class="text-lg font-extrabold tracking-tight" style="color: var(--c-header-ink)">AFMCO</span>
              </template>
            </div>
            <span v-else class="text-lg font-extrabold tracking-tight" style="color: var(--c-header-ink)">Masar</span>

            <div class="flex items-center gap-2 shrink-0">
              <LangToggle variant="header" />
              <span
                class="avatar h-9 w-9 text-sm overflow-hidden"
                style="background: var(--c-header-accent); color: var(--c-header-bg)"
              >
                <img v-if="worker.photo" :src="worker.photo" alt="" class="h-full w-full object-cover" />
                <template v-else>{{ initial }}</template>
              </span>
            </div>
          </div>

          <div class="greeting-block mt-3">
            <p class="text-xs font-semibold uppercase tracking-wider" style="color: var(--c-header-accent)">
              {{ t("common.workerApp") }}
            </p>
            <h1 class="text-xl font-extrabold leading-tight truncate" style="color: var(--c-header-ink)">
              {{ greeting }}<span v-if="firstName">, {{ firstName }}</span>
            </h1>
          </div>
        </div>
      </header>

      <main class="flex-1 px-4 pt-5 pb-28">
        <router-view :ctx="ctx.data" />
      </main>

      <nav class="tabbar" :style="{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }">
        <router-link v-for="tab in tabs" :key="tab.to" :to="tab.to" class="tab">
          <span class="tab-icon-wrap"><Icon :name="tab.icon" :size="22" /></span>
          <span>{{ t(tab.labelKey) }}</span>
          <span class="tab-pip"></span>
        </router-link>
      </nav>
    </template>

    <!-- Error: invalid/disabled token, or a genuine server failure. -->
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
import { computed, watch } from "vue";
import { createResource } from "frappe-ui";
import Icon from "./components/Icon.vue";
import Brand from "./components/Brand.vue";
import LangToggle from "./components/LangToggle.vue";
import { useI18n } from "./i18n";
import { TOKEN, hasToken } from "./token";

const { t, dir } = useI18n();

watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

const ctx = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_context",
  params: { token: TOKEN },
  auto: hasToken,
});

const worker = computed(() => ctx.data && ctx.data.employee && ctx.data);

const firstName = computed(
  () => (ctx.data?.employee_name || "").trim().split(/\s+/)[0] || "",
);
const initial = computed(
  () => (ctx.data?.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("greeting.morning");
  if (h < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

const errorMessage = computed(() => {
  // A PermissionError from the resolver means the link is invalid/disabled.
  const e = ctx.error;
  if (!e) return t("errors.invalidLink");
  const msg = e.messages?.[0] || e.message || "";
  return msg || t("errors.invalidLink");
});

const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

const tabs = [
  { to: "/", icon: "user", labelKey: "nav.profile" },
  { to: "/accommodation", icon: "building", labelKey: "nav.home" },
  { to: "/transport", icon: "route", labelKey: "nav.transport" },
  { to: "/requests", icon: "message", labelKey: "nav.requests" },
];
</script>
