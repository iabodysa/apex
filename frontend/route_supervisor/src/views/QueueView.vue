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
    <WorkQueue :title="t('queue.title')" :eyebrow="t('queue.eyebrow')">
      <ol class="decision-ledger">
        <li v-for="(plan, index) in pendingPlans" :key="plan.name" class="decision-row">
          <router-link
            class="decision-open"
            :to="{ name: 'plan', params: { name: plan.name, tab: 'approval' } }"
          >
            <span class="decision-order"><bdi>{{ String(index + 1).padStart(2, "0") }}</bdi></span>
            <span class="decision-copy">
              <strong>{{ plan.route_name || plan.name }}</strong>
              <span class="decision-evidence">
                <span v-if="plan.project"><Icon name="badge" :size="13" /> {{ plan.project }}</span>
                <span v-if="plan.shift"><Icon name="clock" :size="13" /> {{ t("shift." + plan.shift) }}</span>
                <span><Icon name="pin" :size="13" /> {{ t("list.stops", { n: plan.total_stops }) }}</span>
                <span v-if="plan.driver"><Icon name="user" :size="13" /> {{ plan.driver }}</span>
                <span v-if="plan.vehicle"><Icon name="truck" :size="13" /> <bdi>{{ plan.vehicle }}</bdi></span>
              </span>
            </span>
            <Icon class="decision-chevron" name="chevron" :size="18" />
          </router-link>
          <div class="decision-actions" :aria-label="t('approval.status')">
            <Button
              variant="solid"
              theme="green"
              size="xl"
              :loading="busy"
              :label="t('approval.approve')"
              @click="approvePlan(plan.name)"
            >
              <template #prefix><Icon name="check" :size="16" /></template>
            </Button>
            <Button
              variant="outline"
              theme="red"
              size="xl"
              :disabled="busy"
              :label="t('approval.reject')"
              @click="requestReject(plan.name)"
            >
              <template #prefix><Icon name="x" :size="16" /></template>
            </Button>
          </div>
        </li>
      </ol>
      <div v-if="pendingHasMore" class="ledger-more">
        <Button
          variant="outline"
          size="lg"
          :loading="laneBusy.pending"
          :label="t('common.loadMore')"
          @click="loadNextPending"
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

import Icon from "../Icon.vue";
import { useActions } from "../actions.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const {
  pendingPlans,
  pendingCount,
  activeCount,
  historyCount,
  pendingHasMore,
  laneBusy,
  loadState,
  loadError,
  busy,
  load,
  loadMore,
} = usePlans();
const { approvePlan, requestReject, showToast } = useActions();

const metrics = computed(() => [
  { key: "pending", label: t("kpi.pending"), value: pendingCount.value, tone: "warning" },
  { key: "active", label: t("kpi.active"), value: activeCount.value, tone: "info" },
  { key: "history", label: t("kpi.decided"), value: historyCount.value },
]);

async function loadNextPending() {
  const result = await loadMore("pending");
  if (!result.ok && result.message) showToast(result.message, "bad");
}
const boundaryState = computed(() => {
  if (loadState.value === "loading") return "loading";
  if (loadState.value === "error") return "error";
  if (!pendingPlans.value.length) return "empty";
  return "ready";
});
const boundaryTitle = computed(() =>
  boundaryState.value === "empty" ? t("queue.empty") : t("list.loadError"),
);
const boundaryMessage = computed(() =>
  boundaryState.value === "empty" ? t("queue.emptyHint") : loadError.value,
);
</script>
