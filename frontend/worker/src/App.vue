<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="app-shell" :dir="dir">
    <!-- New build available: a new service worker is installed and waiting. Tap
         reload to activate it; controllerchange then reloads into the new build. -->
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

    <!-- Loading. `&& !worker` is load-bearing: createResource sets loading on EVERY
         fetch, so a bare v-if unmounted the whole routed subtree on each 45s poll
         tick and a half-typed form lost its local state. -->
    <div v-else-if="ctx.loading && !worker" class="flex-1 grid place-items-center p-8">
      <div class="text-center">
        <div class="spinner mx-auto"></div>
        <p class="mt-3 text-sm text-muted">{{ t("common.loading") }}</p>
      </div>
    </div>

    <!-- Resolved worker (Masar): shared Mobile-console archetype — sticky dark
         header, single scrolling card column, sticky ≥52px bottom nav. -->
    <template v-else-if="worker">
      <MobileConsoleShell :title="workerName" :subtitle="greeting" :max-width="480">
        <!-- Header end: language toggle + worker avatar (photo when present). -->
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

        <!-- Scroll column: the routed page. -->
        <router-view :ctx="ctx.data" />

        <!-- Bottom nav (3 primary destinations). isTabActive() keeps Home exact
             and the others inclusive; the shell tints the `.is-active` child. -->
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
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import Icon from "./components/Icon.vue";
// Direct-path (not the @shared/components barrel) so only the shell is pulled
// into the bundle, not every re-exported sibling component.
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

// [T-318] reactive connectivity so the shell can show an offline banner.
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

// Bootstrap read. method:"GET" is load-bearing: frappe-ui defaults to POST, which
// is CSRF-validated and throws CSRFTokenError when window.csrf_token is absent/stale
// at boot (a non-rendered shell or a pre-login PWA-cached shell). get_worker_context
// is a pure read (identity is the token, no commit), so the CSRF-exempt GET path lets
// Masar always load; write calls stay POST+CSRF.
const ctx = createResource({
  url: "apex.salis.api.masar.get_worker_context",
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

const route = useRoute();

const firstName = computed(
  () => (ctx.data?.employee_name || "").trim().split(/\s+/)[0] || "",
);
// Header title = the worker's name; the greeting is the small line above it.
const workerName = computed(() => (ctx.data?.employee_name || "").trim() || firstName.value);
const initial = computed(
  () => (ctx.data?.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

// Bottom-nav highlight: Home ("/") only on the exact root; every other tab is
// active for its whole subtree.
const isTabActive = (tab) =>
  tab.to === "/" ? route.path === "/" : route.path === tab.to || route.path.startsWith(tab.to + "/");

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

// [T-nav] Bottom bar carries only the three primary destinations. The
// secondary sections (accommodation/custody/requests) keep their routes and
// are reached from a links section in Profile.
const tabs = [
  { to: "/", icon: "home", labelKey: "nav.home" },
  { to: "/transport", icon: "route", labelKey: "nav.transport" },
  { to: "/profile", icon: "user", labelKey: "nav.profile" },
];
</script>
