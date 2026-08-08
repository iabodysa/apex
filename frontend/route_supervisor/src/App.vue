<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <TabletSupervisorShell :title="t('list.title')" :subtitle="summary" :menu-label="t('nav.menu')">
    <template #brand>
      <span class="brand-mark"><Brand :size="24" /></span>
      <span class="brand-txt">
        <span class="brand-name">{{ t("brand.name") }}</span>
        <span class="brand-sub">{{ t("brand.sub") }}</span>
      </span>
    </template>

    <template #nav>
      <span class="nav-label">{{ t("nav.work") }}</span>

      <template v-if="selectedName">
        <router-link
          v-for="tb in shownTabs"
          :key="tb.key"
          :to="planRoute(selectedName, tb.key)"
          :class="{ 'is-active': onPlan && tab === tb.key }"
        >
          <Icon :name="tb.icon" :size="17" />
          <span>{{ t("tabs." + tb.key) }}</span>
          <span v-if="tb.key === 'approval' && pendingCount" class="nav-count">{{ pendingCount }}</span>
        </router-link>
      </template>
      <template v-else>
        <button v-for="tb in shownTabs" :key="'off-' + tb.key" type="button" disabled>
          <Icon :name="tb.icon" :size="17" />
          <span>{{ t("tabs." + tb.key) }}</span>
        </button>
      </template>

      <span class="nav-label">{{ t("nav.screens") }}</span>
      <router-link to="/approvals">
        <Icon name="circle-check" :size="17" />
        <span>{{ t("queue.title") }}</span>
        <span v-if="pendingCount" class="nav-count">{{ pendingCount }}</span>
      </router-link>
      <router-link to="/map">
        <Icon name="pin" :size="17" />
        <span>{{ t("fleetMap.title") }}</span>
      </router-link>

      <span class="nav-label">{{ t("nav.account") }}</span>
      <span v-if="supervisorName" class="nav-user">
        <Icon name="user" :size="16" />
        <span>{{ supervisorName }}</span>
      </span>
    </template>

    <template #title-actions>
      <Button
        variant="outline"
        size="lg"
        :label="t('common.refresh')"
        :loading="loadState === 'loading'"
        @click="plans.load()"
      >
        <template #icon><Icon name="refresh" :size="17" /></template>
      </Button>
      <LangToggle />
    </template>

    <template #kpis>
      <div class="kpi">
        <span class="kpi-label">{{ t("kpi.pending") }}</span>
        <b class="kpi-num">{{ pendingCount }}</b>
      </div>
      <div class="kpi">
        <span class="kpi-label">{{ t("kpi.active") }}</span>
        <b class="kpi-num">{{ totalCount }}</b>
      </div>
      <div v-if="selectedBoarding" class="kpi">
        <span class="kpi-label">{{ t("kpi.boarding") }}</span>
        <b class="kpi-num">
          {{ selectedBoarding.boarded }}/{{ selectedBoarding.expected || t("common.none") }}
        </b>
      </div>
    </template>

    <router-view />
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

  <PortalToast :toast="toast" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, Dialog, ErrorMessage, FormControl } from "frappe-ui";

import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import TabletSupervisorShell from "@shared/components/TabletSupervisorShell.vue";
import { useMediaQuery } from "@shared/useBreakpoint.js";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { usePoll } from "@shared/usePoll.js";
import { useToast } from "@shared/useToast.js";

import Icon from "./Icon.vue";
import PortalToast from "./components/PortalToast.vue";
import { provideActions } from "./actions.js";
import { connectRouteSupervisorRealtime } from "./realtime.js";
import { createPlansStore } from "./usePlans.js";
import { TAB_ICONS, TAB_KEYS, tabsFor } from "./tabs.js";
import { useI18n } from "@/i18n";

const { t, lang, dir } = useI18n();
useDocumentLanguage(lang, dir);

const route = useRoute();
const router = useRouter();
const plans = createPlansStore();
const { loadState, pendingCount, totalCount, supervisorName, busy } = plans;
const { toast, showToast } = useToast();

const wide = useMediaQuery("(min-width: 1280px)");
const shownTabs = computed(() =>
  tabsFor(wide.value).map((key) => ({ key, icon: TAB_ICONS[key] })),
);

const onPlan = computed(() => route.name === "plan");
const selectedName = computed(() => (onPlan.value ? String(route.params.name) : ""));
const askedTab = computed(() => (onPlan.value ? String(route.params.tab || "") : ""));
const tab = computed(() =>
  shownTabs.value.some((tb) => tb.key === askedTab.value) ? askedTab.value : TAB_KEYS[0],
);

const selectedPlan = computed(() => plans.planByName(selectedName.value));
const selectedBoarding = computed(() => selectedPlan.value?.trip?.boarding || null);
const summary = computed(() =>
  t("header.summary", { p: pendingCount.value, t: totalCount.value }),
);

const planRoute = (name, key) => ({ name: "plan", params: { name, tab: key } });

/* A shared link that names a tab this width does not offer, or names none at all, is rewritten
   rather than left pointing at nothing. Replace, not push: the reader did not navigate. */
watch(
  [askedTab, shownTabs, selectedName],
  () => {
    if (!onPlan.value || !selectedName.value) return;
    if (askedTab.value !== tab.value) {
      router.replace(planRoute(selectedName.value, tab.value));
    }
  },
  { immediate: true },
);

const rejectOpen = ref(false);
const rejectReason = ref("");
const rejectError = ref("");
/* The plan the dialog is about. Holding it here instead of moving the selection is what stops a
   rejection raised from the queue from navigating the supervisor out of the queue. */
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
  showToast(res.ok ? t("approval.approvedToast") : res.message || t("approval.actionError"),
    res.ok ? "ok" : "bad");
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
