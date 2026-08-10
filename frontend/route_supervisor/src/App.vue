<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <FrappeUIProvider>
    <a class="supervisor-skip" href="#supervisor-main">{{ t("nav.skip") }}</a>

    <TabletSupervisorShell
      :title="sceneTitle"
      :subtitle="sceneEyebrow"
      :menu-label="t('nav.menu')"
      accent="var(--c-mint)"
      nav-width="15rem"
    >
      <template #brand>
        <Brand variant="reverse" :size="36" />
        <span class="portal-brand-copy">
          <strong>{{ t("brand.name") }}</strong>
          <span>{{ t("brand.sub") }}</span>
        </span>
      </template>

      <template #title-actions>
        <span v-if="supervisorName" class="portal-user">
          <Icon name="user" :size="16" />
          <bdi dir="auto">{{ supervisorName }}</bdi>
        </span>
        <Button
          variant="outline"
          size="lg"
          :aria-label="t('common.refresh')"
          :loading="loadState === 'loading'"
          @click="plans.load()"
        >
          <template #icon><Icon name="refresh" :size="17" /></template>
        </Button>
        <LangToggle variant="header" />
      </template>

      <template #nav>
        <router-link
          to="/approvals"
          :class="{ 'is-active': navSection === 'inbox' }"
          :aria-current="navSection === 'inbox' ? 'page' : undefined"
        >
          <Icon name="circle-check" :size="18" />
          <span>{{ t("nav.inbox") }}</span>
          <Badge
            v-if="pendingCount"
            class="nav-count"
            theme="green"
            variant="subtle"
            size="lg"
            :label="pendingCount"
          />
        </router-link>
        <router-link
          to="/routes"
          :class="{ 'is-active': navSection === 'routes' }"
          :aria-current="navSection === 'routes' ? 'page' : undefined"
        >
          <Icon name="route" :size="18" />
          <span>{{ t("nav.routes") }}</span>
        </router-link>
        <router-link
          to="/map"
          :class="{ 'is-active': navSection === 'map' }"
          :aria-current="navSection === 'map' ? 'page' : undefined"
        >
          <Icon name="pin" :size="18" />
          <span>{{ t("nav.liveFleet") }}</span>
        </router-link>
        <router-link
          to="/history"
          :class="{ 'is-active': navSection === 'history' }"
          :aria-current="navSection === 'history' ? 'page' : undefined"
        >
          <Icon name="clipboard-check" :size="18" />
          <span>{{ t("nav.history") }}</span>
        </router-link>
      </template>

      <main id="supervisor-main" class="supervisor-main" tabindex="-1">
        <p v-if="sceneSubtitle" class="supervisor-intro">
          <bdi dir="auto">{{ sceneSubtitle }}</bdi>
        </p>
        <router-view />
      </main>
    </TabletSupervisorShell>

    <Dialog v-model="rejectOpen" :options="rejectOptions" @close="closeReject">
      <template #body-content>
        <p class="modal-sub">{{ t("approval.rejectPrompt") }}</p>
        <FormControl
          v-model="rejectReason"
          type="textarea"
          size="md"
          :rows="4"
          :label="t('approval.reason')"
          :placeholder="t('approval.rejectPlaceholder')"
        />
        <ErrorMessage class="mt-2" :message="rejectError" />
      </template>
    </Dialog>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  Badge,
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  FrappeUIProvider,
  toast,
} from "frappe-ui";

import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import TabletSupervisorShell from "@shared/components/TabletSupervisorShell.vue";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { usePoll } from "@shared/usePoll.js";

import Icon from "./Icon.vue";
import { provideActions } from "./actions.js";
import { laneForPlan } from "./planLanes.js";
import { connectRouteSupervisorRealtime } from "./realtime.js";
import { createPlansStore } from "./usePlans.js";
import { useI18n } from "@/i18n";

const { t, lang, dir } = useI18n();
useDocumentLanguage(lang, dir);

const route = useRoute();
const plans = createPlansStore();
const { loadState, pendingCount, activeCount, supervisorName, busy } = plans;

function showToast(message, type = "ok") {
  toast.create({
    message,
    type: type === "ok" ? "success" : type === "bad" ? "error" : "info",
    duration: 3.5,
  });
}

const selectedPlan = computed(() =>
  route.name === "plan" ? plans.planByName(String(route.params.name || "")) : null,
);
const selectedSection = computed(() => {
  if (!selectedPlan.value) return "routes";
  return ({ pending: "inbox", active: "routes", history: "history" })[
    laneForPlan(selectedPlan.value)
  ];
});
const navSection = computed(() => {
  if (route.name === "plan") return selectedSection.value;
  return ({ approvals: "inbox", routes: "routes", map: "map", history: "history" })[route.name] || "inbox";
});

const sceneTitle = computed(() => {
  if (route.name === "plan") return "";
  return t(`scenes.${navSection.value}.title`);
});
const sceneEyebrow = computed(() => (route.name === "plan" ? "" : t("scenes.eyebrow")));
const sceneSubtitle = computed(() => {
  if (route.name === "plan") return "";
  if (navSection.value === "inbox") return t("scenes.inbox.subtitle", { n: pendingCount.value });
  if (navSection.value === "routes") {
    return t("scenes.routes.subtitle", { n: activeCount.value });
  }
  return t(`scenes.${navSection.value}.subtitle`);
});

const rejectOpen = ref(false);
const rejectReason = ref("");
const rejectError = ref("");
const rejectTarget = ref("");

const rejectOptions = computed(() => ({
  title: t("approval.rejectTitle"),
  size: "md",
  actions: [
    {
      label: t("approval.rejectConfirm"),
      variant: "solid",
      theme: "red",
      onClick: confirmReject,
    },
    { label: t("common.cancel"), variant: "outline", onClick: ({ close }) => close() },
  ],
}));

function requestReject(name) {
  rejectTarget.value = name;
  rejectReason.value = "";
  rejectError.value = "";
  rejectOpen.value = true;
}

function closeReject() {
  rejectOpen.value = false;
  rejectTarget.value = "";
  rejectError.value = "";
}

async function confirmReject({ close }) {
  const reason = rejectReason.value.trim();
  if (!reason) {
    rejectError.value = t("approval.reasonRequired");
    return;
  }
  const res = await plans.reject(rejectTarget.value, reason);
  if (!res.ok) {
    rejectError.value = res.message || t("approval.actionError");
    return;
  }
  close();
  closeReject();
  showToast(t("approval.rejectedToast"), "ok");
}

async function approvePlan(name) {
  const res = await plans.approve(name);
  showToast(
    res.ok ? t("approval.approvedToast") : res.message || t("approval.actionError"),
    res.ok ? "ok" : "bad",
  );
}

provideActions({ approvePlan, requestReject, showToast });

const POLL_MS = 45000;
usePoll(() => {
  if (!busy.value && !rejectOpen.value) plans.load();
}, POLL_MS);

let stopRealtime = null;
onMounted(() => {
  plans.load();
  stopRealtime = connectRouteSupervisorRealtime(() => {
    if (!busy.value && !rejectOpen.value) plans.load();
  });
});
onUnmounted(() => {
  if (stopRealtime) stopRealtime();
});
</script>
