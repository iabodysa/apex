<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <AsyncBoundary
    :state="pageState"
    :title="pageTitle"
    :message="pageMessage"
    :retry-label="t('common.retry')"
    @retry="load"
  >
    <Alert
      v-if="errors.length && pageState !== 'error'"
      class="overview-alert"
      theme="yellow"
      :title="t('today.partialTitle')"
      :description="t('today.partialHint')"
      :dismissable="false"
    />

    <MetricRibbon v-if="metrics.length" :metrics="metrics" />

    <div class="overview-layout">
      <section class="overview-lead">
        <p class="overview-kicker">{{ t("today.now") }}</p>
        <h2>{{ leadTitle }}</h2>
        <p>{{ leadHint }}</p>

        <div v-if="localWork.total" class="local-work" role="status">
          <Icon name="shield" :size="18" />
          <span>{{ t("today.localWork", { n: localWork.total }) }}</span>
        </div>
      </section>

      <WorkQueue :title="t('today.queueTitle')" :eyebrow="t('today.queueEyebrow')">
        <router-link
          v-for="item in workItems"
          :key="item.key"
          class="overview-row"
          :to="item.path"
        >
          <span class="overview-row-icon"><Icon :name="item.icon" :size="20" /></span>
          <span class="overview-row-copy">
            <strong>{{ item.title }}</strong>
            <small>{{ item.hint }}</small>
          </span>
          <span class="overview-row-value" :data-tone="item.tone">
            <bdi dir="auto">{{ item.value }}</bdi>
          </span>
          <Icon name="chevron" :size="18" />
        </router-link>
      </WorkQueue>
    </div>

    <nav class="domain-ledger" :aria-label="t('today.openDomain')">
      <router-link v-for="link in domainLinks" :key="link.key" :to="link.path">
        <span>
          <strong>{{ link.title }}</strong>
          <small>{{ link.hint }}</small>
        </span>
        <Icon name="chevron" :size="18" />
      </router-link>
    </nav>
  </AsyncBoundary>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Alert, createResource } from "frappe-ui";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import MetricRibbon from "@shared/components/MetricRibbon.vue";
import WorkQueue from "@shared/components/WorkQueue.vue";
import Icon from "../components/Icon.vue";
import { readCountDraft, readRoundDraft } from "../drafts.js";
import { useI18n, resourceErrorMessage } from "../i18n";
import { hasSection } from "../portal.js";
import { connectSafetyRealtime } from "../realtime.js";
import { building, localDate } from "../session";
import {
  countRoundMarks,
  draftCount,
  occupancyMetrics,
  pendingArrivals,
  todayPageState,
} from "../today.js";

const { t } = useI18n();

const localCountDraft = ref(0);
const localRoundDraft = ref(0);

const gridRes = createResource({
  url: "apex.habitat.api.front_desk.get_building_grid",
  makeParams: () => ({ building: building.value }),
});
const requestsRes = createResource({
  url: "apex.habitat.api.front_desk.building_open_requests",
  makeParams: () => ({ building: building.value }),
});
const arrivalsRes = createResource({
  url: "apex.habitat.api.arrivals_desk.get_expected_arrivals",
  makeParams: () => ({ date: localDate(), building: building.value }),
});
const safetyRes = createResource({
  url: "apex.habitat.api.safety_checklist.get_due_cadences",
  makeParams: () => ({ building: building.value }),
});

const enabled = {
  grid: hasSection("beds") || hasSection("transfer"),
  requests: hasSection("beds"),
  arrivals: hasSection("arrivals"),
  safety: hasSection("safety"),
};

const resources = computed(() => [
  ...(enabled.grid ? [gridRes] : []),
  ...(enabled.requests ? [requestsRes] : []),
  ...(enabled.arrivals ? [arrivalsRes] : []),
  ...(enabled.safety ? [safetyRes] : []),
]);
const errors = computed(() => resources.value.filter((resource) => resource.error));
const loading = computed(() => resources.value.some((resource) => resource.loading));
const loadedCount = computed(
  () => resources.value.filter((resource) => resource.data != null).length,
);
const pageState = computed(() =>
  todayPageState({
    loading: loading.value,
    loaded: loadedCount.value,
    failed: errors.value.length,
    total: resources.value.length,
  }),
);
const pageTitle = computed(() =>
  pageState.value === "error" ? t("today.loadErrorTitle") : t("today.loadingTitle"),
);
/* The landing screen used to blame the network for every failure, including a building the
   site has never heard of. It now reads the server's own answer, so the one cause a person
   can act on is named instead of hidden behind "check your connection". */
const pageMessage = computed(() => {
  if (pageState.value !== "error") return t("today.loadingHint");
  const first = errors.value[0];
  return first
    ? resourceErrorMessage(first.error, "today.loadErrorHint")
    : t("today.loadErrorHint");
});

const gridReady = computed(() => gridRes.data != null);
const requestsReady = computed(() => requestsRes.data != null);
const arrivalsReady = computed(() => arrivalsRes.data != null);
const safetyReady = computed(() => safetyRes.data != null);

const occupancy = computed(() => occupancyMetrics(gridRes.data && gridRes.data.summary));
const arrivalsPending = computed(() => pendingArrivals(arrivalsRes.data));
const openRequests = computed(() => Number((requestsRes.data && requestsRes.data.open_requests) || 0));
const dueBlocks = computed(() => (safetyRes.data && safetyRes.data.due) || []);
const dueTasks = computed(() =>
  dueBlocks.value.reduce((total, block) => total + (Array.isArray(block.tasks) ? block.tasks.length : 0), 0),
);
const localWork = computed(() => ({
  counts: localCountDraft.value,
  rounds: localRoundDraft.value,
  total: localCountDraft.value + localRoundDraft.value,
}));

const metrics = computed(() => {
  const items = [];
  if (enabled.grid && gridReady.value) {
    items.push({ label: t("today.occupied"), value: `${occupancy.value.occupied}/${occupancy.value.total}` });
    items.push({ label: t("today.available"), value: occupancy.value.available, tone: "success" });
  }
  if (enabled.arrivals && arrivalsReady.value) {
    items.push({
      label: t("today.arrivals"),
      value: arrivalsPending.value,
      tone: arrivalsPending.value ? "info" : "success",
    });
  }
  if (enabled.safety && safetyReady.value) {
    items.push({
      label: t("today.safetyTasks"),
      value: dueTasks.value,
      tone: dueTasks.value ? "warning" : "success",
    });
  }
  return items;
});

const workItems = computed(() => {
  const items = [];
  if (enabled.arrivals) {
    items.push({
      key: "arrivals",
      path: "/arrivals",
      icon: "user",
      title: t("today.arrivalTask"),
      hint: t("today.arrivalTaskHint"),
      value: arrivalsReady.value ? arrivalsPending.value : "—",
      tone: arrivalsPending.value ? "info" : "quiet",
    });
  }
  if (enabled.requests) {
    items.push({
      key: "requests",
      path: "/beds",
      icon: "bed",
      title: t("today.residentTask"),
      hint: t("today.residentTaskHint"),
      value: requestsReady.value ? openRequests.value : "—",
      tone: openRequests.value ? "warning" : "quiet",
    });
  }
  if (hasSection("count")) {
    items.push({
      key: "count",
      path: "/count",
      icon: "clipboard-check",
      title: t("today.countTask"),
      hint: localCountDraft.value ? t("today.countDraftHint") : t("today.countTaskHint"),
      value: localCountDraft.value,
      tone: localCountDraft.value ? "info" : "quiet",
    });
  }
  if (enabled.safety) {
    items.push({
      key: "safety",
      path: "/safety",
      icon: "shield-check",
      title: t("today.safetyTask"),
      hint: localRoundDraft.value ? t("today.roundDraftHint") : t("today.safetyTaskHint"),
      value: safetyReady.value ? dueTasks.value : "—",
      tone: dueTasks.value ? "warning" : "quiet",
    });
  }
  return items;
});

const leadTitle = computed(() => {
  if (safetyReady.value && dueTasks.value) return t("today.leadSafety", { n: dueTasks.value });
  if (arrivalsReady.value && arrivalsPending.value) {
    return t("today.leadArrivals", { n: arrivalsPending.value });
  }
  if (requestsReady.value && openRequests.value) {
    return t("today.leadRequests", { n: openRequests.value });
  }
  if (errors.value.length) return t("today.partialTitle");
  return t("today.leadClear");
});
const leadHint = computed(() => {
  if (localWork.value.total) return t("today.leadDraftHint");
  return errors.value.length ? t("today.partialHint") : t("today.leadHint");
});

const domainLinks = computed(() => {
  const links = [];
  if (hasSection("beds") || hasSection("arrivals") || hasSection("transfer")) {
    links.push({
      key: "residents",
      path: hasSection("beds") ? "/beds" : hasSection("arrivals") ? "/arrivals" : "/transfer",
      title: t("nav.residents"),
      hint: t("today.residentsHint"),
    });
  }
  if (hasSection("custody") || hasSection("count") || hasSection("delivery")) {
    links.push({
      key: "assets",
      path: hasSection("custody") ? "/custody" : hasSection("count") ? "/count" : "/delivery",
      title: t("nav.assets"),
      hint: t("today.assetsHint"),
    });
  }
  if (hasSection("safety")) {
    links.push({
      key: "safety",
      path: "/safety",
      title: t("nav.safety"),
      hint: t("today.safetyHint"),
    });
  }
  return links;
});

function refreshDrafts() {
  localCountDraft.value = hasSection("count") ? draftCount(readCountDraft(building.value)) : 0;
  localRoundDraft.value = hasSection("safety")
    ? countRoundMarks(readRoundDraft(building.value, localDate()))
    : 0;
}

function load() {
  if (!building.value) return;
  refreshDrafts();
  if (enabled.grid) gridRes.fetch();
  if (enabled.requests) requestsRes.fetch();
  if (enabled.arrivals) arrivalsRes.fetch();
  if (enabled.safety) safetyRes.fetch();
}

let stopRealtime = () => {};
onMounted(() => {
  load();
  window.addEventListener("focus", refreshDrafts);
  if (enabled.safety) {
    stopRealtime = connectSafetyRealtime(() => safetyRes.reload());
  }
});
onUnmounted(() => {
  window.removeEventListener("focus", refreshDrafts);
  stopRealtime();
});
watch(building, load);
</script>

<style scoped>
.overview-alert {
  margin-block-end: var(--sp-5);
}
.overview-layout {
  display: grid;
  gap: clamp(var(--sp-6), 5vw, 4rem);
  margin-block-start: clamp(var(--sp-6), 5vw, 4rem);
}
.overview-lead {
  align-self: start;
  padding-block-start: var(--sp-4);
  border-block-start: 4px solid var(--c-primary);
}
.overview-kicker {
  margin: 0 0 var(--sp-2);
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
}
.overview-lead h2 {
  max-inline-size: 17ch;
  margin: 0;
  color: var(--c-ink);
  font-family: var(--font-display);
  font-size: clamp(1.75rem, 2.6vw, 3.2rem);
  font-weight: 700;
  line-height: 1.15;
  text-wrap: balance;
}
.overview-lead > p:not(.overview-kicker) {
  max-inline-size: 38rem;
  margin: var(--sp-3) 0 0;
  color: var(--c-ink-soft);
  font-family: var(--font-serif);
  font-size: 1.05rem;
  line-height: 1.75;
  text-wrap: pretty;
}
.local-work {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-block-start: var(--sp-5);
  padding-block: var(--sp-3);
  border-block: 1px solid var(--c-border-strong);
  color: var(--c-accent-ink);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.overview-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: 72px;
  padding-block: var(--sp-3);
  color: inherit;
  text-decoration: none;
}
.overview-row-icon {
  display: grid;
  place-items: center;
  inline-size: var(--tap-min);
  block-size: var(--tap-min);
  color: var(--c-primary);
}
.overview-row-copy {
  display: grid;
  min-inline-size: 0;
  gap: 2px;
}
.overview-row-copy strong {
  color: var(--c-ink);
  font-size: var(--fs-body);
}
.overview-row-copy small {
  color: var(--c-muted);
  font-family: var(--font-serif);
  font-size: var(--fs-sm);
  line-height: 1.5;
}
.overview-row-value {
  min-inline-size: 2.25rem;
  color: var(--c-muted);
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  text-align: center;
}
.overview-row-value[data-tone="warning"] { color: var(--c-warning); }
.overview-row-value[data-tone="info"] { color: var(--c-info); }
.domain-ledger {
  display: grid;
  margin-block-start: clamp(var(--sp-6), 5vw, 4rem);
  border-block: 1px solid var(--c-border-strong);
}
.domain-ledger a {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: 76px;
  padding-block: var(--sp-3);
  color: inherit;
  text-decoration: none;
}
.domain-ledger a + a {
  border-block-start: 1px solid var(--c-border);
}
.domain-ledger a > span {
  display: grid;
  flex: 1;
  gap: 2px;
}
.domain-ledger strong {
  color: var(--c-ink);
  font-size: var(--fs-body);
}
.domain-ledger small {
  color: var(--c-muted);
  font-family: var(--font-serif);
  line-height: 1.5;
}

@media (min-width: 64rem) {
  .overview-layout {
    grid-template-columns: minmax(18rem, 0.8fr) minmax(26rem, 1.2fr);
  }
  .domain-ledger {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .domain-ledger a {
    padding-inline: var(--sp-5);
  }
  .domain-ledger a + a {
    border-block-start: 0;
    border-inline-start: 1px solid var(--c-border);
  }
}
</style>
