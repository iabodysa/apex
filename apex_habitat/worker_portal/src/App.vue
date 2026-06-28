<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="app-shell" :dir="dir">
    <!-- New build available: a new service worker is installed and waiting. Tap
         reload to activate it; controllerchange then reloads into the new build. -->
    <div
      v-if="updateReady"
      class="flex items-center justify-center gap-2 text-xs font-semibold"
      style="background: var(--c-accent, #00844e); color: #fff; padding: 8px 12px"
    >
      <Icon name="refresh" :size="14" />
      <span>{{ t("update.available") }}</span>
      <button class="font-bold underline" style="padding-inline: 6px" @click="applyUpdate">
        {{ t("update.reload") }}
      </button>
    </div>

    <!-- [T-318] offline banner: tell the worker we are showing last-known info
         when the device drops its connection. -->
    <div
      v-if="!online"
      class="flex items-center justify-center gap-2 text-xs font-semibold"
      style="background: var(--c-warning-bg); color: var(--c-warning); padding: 6px 12px"
    >
      <Icon name="alert" :size="14" />
      <span>{{ t("common.offline") }}</span>
    </div>

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
              {{ greeting }}<span v-if="firstName">, <bdi>{{ firstName }}</bdi></span>
            </h1>
          </div>
        </div>
      </header>

      <main class="flex-1 px-4 pt-5 pb-28">
        <router-view :ctx="ctx.data" />
      </main>

      <nav class="tabbar" :style="{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }">
        <router-link v-for="tab in tabs" :key="tab.to" :to="tab.to" class="tab">
          <span class="tab-icon-wrap"><Icon :name="tab.icon" :size="22" :class="{ 'rtl-flip': tab.icon === 'route' }" /></span>
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
import { computed, watch, ref, onMounted, onUnmounted } from "vue";
import { createResource } from "frappe-ui";
import Icon from "./components/Icon.vue";
import Brand from "./components/Brand.vue";
import LangToggle from "./components/LangToggle.vue";
import { useI18n, resourceErrorMessage, setEnumLabels } from "./i18n";
import { TOKEN, hasToken } from "./token";
import { updateReady, applyUpdate, initPwaUpdates } from "./pwa";
import { usePoll } from "./usePoll";

const { t, dir } = useI18n();

// Server-driven enum labels (DocType Select options + ar.csv), fetched once and
// registered into i18n so tEnum localizes without a hand-maintained JS map.
// English needs none (the label is the stored value), so only Arabic is loaded.
const enumLabels = createResource({
  url: "apex_habitat.salis.api.masar.get_enum_labels",
  method: "GET",
  params: { lang: "ar" },
  auto: true,
  onSuccess: (data) => setEnumLabels("ar", data),
});

watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// [T-318] reactive connectivity so the shell can show an offline banner.
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const syncOnline = () => (online.value = navigator.onLine);
onMounted(() => {
  window.addEventListener("online", syncOnline);
  window.addEventListener("offline", syncOnline);
  initPwaUpdates();
});
onUnmounted(() => {
  window.removeEventListener("online", syncOnline);
  window.removeEventListener("offline", syncOnline);
});

// Bootstrap read. method:"GET" is load-bearing: frappe-ui defaults to POST, which
// is CSRF-validated and throws CSRFTokenError when window.csrf_token is absent/stale
// at boot (a non-rendered shell or a pre-login PWA-cached shell). get_worker_context
// is a pure read (identity is the token, no commit), so the CSRF-exempt GET path lets
// Masar always load; write calls stay POST+CSRF.
const ctx = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_context",
  method: "GET",
  params: { token: TOKEN },
  auto: hasToken,
});

const worker = computed(() => ctx.data && ctx.data.employee && ctx.data);

// Auto-update for this GUEST portal: a guest has no Desk session and so cannot
// join Frappe's permission-gated Socket.IO doctype rooms for server push — the
// honest substitute is a foreground poll. Re-run the bootstrap context (the same
// token-scoped read the app already loads; pages render off `ctx.data`) so an
// upcoming-trip / "driver arrived" (P-046) change surfaces without a manual
// pull-to-refresh. Reuses ctx.reload() — no new endpoint. Only when a token is
// present (no point polling the "no link" / error shell). The composable keeps
// it cheap: visible-only, refetch-on-show, no overlap, torn down on unmount.
if (hasToken) usePoll(() => ctx.reload());

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

// A transient transport failure (rate limit / stale CSRF) is NOT a bad link —
// mapping it to "invalid link" wrongly tells the worker to get a new link. Only
// a real PermissionError (or an explicit server message) drives the
// "invalid/disabled link" copy; transient failures get a retry-able message.
const errorMessage = computed(() => resourceErrorMessage(ctx.error, "errors.invalidLink"));

const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

// [T-nav] Bottom bar carries only the three primary destinations. The
// secondary sections (accommodation/custody/requests) keep their routes and
// are reached from a links section in Profile.
const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
  { to: "/transport", icon: "route", labelKey: "nav.transport" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
];
</script>
