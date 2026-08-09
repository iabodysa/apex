<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <template v-if="!selectedName">
    <MetricRibbon :metrics="routeMetrics" />
    <AsyncBoundary
      :state="directoryState"
      :title="directoryTitle"
      :message="directoryMessage"
      :retry-label="t('common.retry')"
      @retry="load()"
    >
      <WorkQueue :title="t('routes.ledger')" :eyebrow="t('routes.eyebrow')">
        <PlanList :items="activePlans" mode="active" />
        <div v-if="decidedHasMore" class="ledger-more">
          <Button
            variant="outline"
            size="lg"
            :loading="laneBusy.decided"
            :label="t('common.loadMore')"
            @click="loadNextDecided"
          />
        </div>
      </WorkQueue>
    </AsyncBoundary>
  </template>

  <div v-else-if="selectedPlan" class="plan-workspace">
    <aside class="plan-workspace-queue">
      <WorkQueue :title="contextTitle" :eyebrow="contextEyebrow">
        <PlanList :items="contextPlans" :selected-name="selectedName" :mode="contextMode" />
        <div v-if="contextHasMore" class="ledger-more">
          <Button
            variant="outline"
            size="lg"
            :loading="laneBusy[contextLane]"
            :label="t('common.loadMore')"
            @click="loadContextLane"
          />
        </div>
      </WorkQueue>
    </aside>

    <PlanDetail
      class="plan-workspace-stage"
      :plan="selectedPlan"
      :tab="tab"
      :wide="wide"
      :back-to="backTo"
    />

    <EvidenceRail
      v-if="showEvidence"
      class="plan-workspace-evidence"
      :title="t('map.title')"
      :eyebrow="t('evidence.live')"
    >
      <DriverMap :trip-name="selectedTrip" :active="true" compact />
    </EvidenceRail>
  </div>

  <AsyncBoundary
    v-else
    :state="selectionState"
    :title="selectionTitle"
    :message="selectionMessage"
    :retry-label="t('common.retry')"
    @retry="load()"
  >
    <template #state>
      <Button variant="outline" size="xl" :label="t('nav.inbox')" @click="router.push('/approvals')" />
    </template>
  </AsyncBoundary>
</template>

<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button } from "frappe-ui";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import EvidenceRail from "@shared/components/EvidenceRail.vue";
import MetricRibbon from "@shared/components/MetricRibbon.vue";
import WorkQueue from "@shared/components/WorkQueue.vue";
import { useMediaQuery } from "@shared/useBreakpoint.js";

import DriverMap from "../components/DriverMap.vue";
import PlanDetail from "../components/PlanDetail.vue";
import PlanList from "../components/PlanList.vue";
import { useActions } from "../actions.js";
import { laneForPlan } from "../planLanes.js";
import { pagedSubsetState } from "../planPages.js";
import { usePlans } from "../usePlans.js";
import { TAB_KEYS, tabsFor } from "../tabs.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const {
  activePlans,
  activeCount,
  pendingPlans,
  historyPlans,
  planByName,
  pendingHasMore,
  decidedHasMore,
  laneBusy,
  loadState,
  loadError,
  load,
  ensurePlan,
  loadMore,
  targetLoadState,
  targetLoadError,
} = usePlans();
const { showToast } = useActions();

const wide = useMediaQuery("(min-width: 84rem)");
const showEvidence = wide;
const selectedName = computed(() => (route.name === "plan" ? String(route.params.name || "") : ""));
const selectedPlan = computed(() => (selectedName.value ? planByName(selectedName.value) : null));
const selectedTrip = computed(() => selectedPlan.value?.trip?.name || null);

const contextMode = computed(() => {
  return selectedPlan.value ? laneForPlan(selectedPlan.value) : "active";
});
const contextPlans = computed(() => {
  if (contextMode.value === "pending") return pendingPlans.value;
  if (contextMode.value === "history") return historyPlans.value;
  return activePlans.value;
});
const contextLane = computed(() => (contextMode.value === "pending" ? "pending" : "decided"));
const contextHasMore = computed(() =>
  contextLane.value === "pending" ? pendingHasMore.value : decidedHasMore.value,
);
const contextTitle = computed(() => t(`${contextMode.value}.ledger`));
const contextEyebrow = computed(() => t(`${contextMode.value}.eyebrow`));
const backTo = computed(() =>
  contextMode.value === "pending" ? "/approvals" : contextMode.value === "history" ? "/history" : "/routes",
);

async function loadLane(lane) {
  const result = await loadMore(lane);
  if (!result.ok && result.message) showToast(result.message, "bad");
}

const loadNextDecided = () => loadLane("decided");
const loadContextLane = () => loadLane(contextLane.value);

watch(
  selectedName,
  (name) => {
    if (name) ensurePlan(name);
  },
  { immediate: true },
);

const tab = computed(() => {
  const asked = String(route.params.tab || "");
  return tabsFor(wide.value).includes(asked) ? asked : TAB_KEYS[0];
});

watch(
  [selectedName, tab],
  () => {
    if (!selectedName.value) return;
    const asked = String(route.params.tab || "");
    if (asked !== tab.value) {
      router.replace({ name: "plan", params: { name: selectedName.value, tab: tab.value } });
    }
  },
  { immediate: true },
);

const routeMetrics = computed(() => [
  { key: "active", label: t("kpi.active"), value: activeCount.value, tone: "info" },
  {
    key: "dispatched",
    label: t("routes.dispatched"),
    value: activePlans.value.filter((plan) => plan.trip?.status === "Dispatched").length,
    tone: "warning",
  },
  {
    key: "planned",
    label: t("routes.planned"),
    value: activePlans.value.filter((plan) => !plan.trip || plan.trip?.status === "Planned").length,
  },
]);
const directoryState = computed(() =>
  pagedSubsetState({
    loadState: loadState.value,
    itemCount: activePlans.value.length,
    hasMore: decidedHasMore.value,
  }),
);
const directoryTitle = computed(() =>
  directoryState.value === "empty" ? t("routes.empty") : t("list.loadError"),
);
const directoryMessage = computed(() =>
  directoryState.value === "empty" ? t("routes.emptyHint") : loadError.value,
);
const selectionState = computed(() => {
  if (targetLoadState.value === "loading") return "loading";
  if (targetLoadState.value === "error") return "error";
  if (loadState.value === "loading") return "loading";
  if (loadState.value === "error") return "error";
  return "empty";
});
const selectionTitle = computed(() =>
  selectionState.value === "error" ? t("list.loadError") : t("list.gonePlan"),
);
const selectionMessage = computed(() =>
  selectionState.value === "error"
    ? targetLoadError.value || loadError.value
    : t("list.gonePlanHint"),
);
</script>
