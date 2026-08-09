<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <MetricRibbon :metrics="metrics" />

  <AsyncBoundary
    :state="boundaryState"
    :title="boundaryTitle"
    :message="boundaryMessage"
    :retry-label="t('common.retry')"
    @retry="load()"
  >
    <WorkQueue :title="t('history.ledger')" :eyebrow="t('history.eyebrow')">
      <PlanList :items="historyPlans" mode="history" />
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

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import MetricRibbon from "@shared/components/MetricRibbon.vue";
import WorkQueue from "@shared/components/WorkQueue.vue";

import PlanList from "../components/PlanList.vue";
import { useActions } from "../actions.js";
import { pagedSubsetState } from "../planPages.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const {
  historyPlans,
  historyCount,
  decidedHasMore,
  laneBusy,
  loadState,
  loadError,
  load,
  loadMore,
} = usePlans();
const { showToast } = useActions();

const rejectedCount = computed(
  () => historyPlans.value.filter((plan) => plan.approval === "Rejected").length,
);
const completedCount = computed(
  () => historyPlans.value.filter((plan) => plan.trip?.status === "Completed").length,
);
const metrics = computed(() => [
  { key: "decided", label: t("history.decided"), value: historyCount.value },
  { key: "completed", label: t("history.completed"), value: completedCount.value, tone: "success" },
  { key: "rejected", label: t("history.rejected"), value: rejectedCount.value, tone: "danger" },
]);

async function loadNextDecided() {
  const result = await loadMore("decided");
  if (!result.ok && result.message) showToast(result.message, "bad");
}
const boundaryState = computed(() =>
  pagedSubsetState({
    loadState: loadState.value,
    itemCount: historyPlans.value.length,
    hasMore: decidedHasMore.value,
  }),
);
const boundaryTitle = computed(() =>
  boundaryState.value === "empty" ? t("history.empty") : t("list.loadError"),
);
const boundaryMessage = computed(() =>
  boundaryState.value === "empty" ? t("history.emptyHint") : loadError.value,
);
</script>
