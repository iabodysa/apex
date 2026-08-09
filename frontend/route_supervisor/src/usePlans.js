// Copyright (c) 2026, afmcoltd
import { computed, inject, provide, ref } from "vue";

import {
  approveRoutePlan,
  getSupervisorContext,
  getSupervisorPlan,
  getSupervisorPlans,
  rejectRoutePlan,
} from "./api.js";
import { createSequence } from "./fmt.js";
import { isActivePlan, isHistoryPlan, isPendingPlan } from "./planLanes.js";
import { loadedForLane, mergePlanPage } from "./planPages.js";
import { resourceErrorMessage } from "@/i18n";

const PLANS = Symbol("apex.route-supervisor.plans");

/* One store for the plan list, its counters and the two decisions, created once at the root and
   handed to the views through provide/inject. Two stores would mean a plan decided in the queue
   stays Pending in the detail until the next poll. */
export function createPlansStore() {
  const ctx = ref(null);
  const loadState = ref("loading");
  const loadError = ref("");
  const busy = ref(false);
  const laneBusy = ref({ pending: false, decided: false });
  const targetedPlans = ref([]);
  const targetLoadState = ref("idle");
  const targetLoadError = ref("");
  const seq = createSequence();
  const targetSeq = createSequence();

  const plans = computed(() => mergePlanPage(ctx.value?.plans || [], targetedPlans.value));
  const pendingPlans = computed(() => plans.value.filter(isPendingPlan));
  const historyPlans = computed(() => plans.value.filter(isHistoryPlan));
  const activePlans = computed(() => plans.value.filter(isActivePlan));
  const pendingCount = computed(() => ctx.value?.counts?.pending || 0);
  const decidedCount = computed(() => ctx.value?.counts?.decided || 0);
  const activeCount = computed(() => ctx.value?.counts?.active || 0);
  const historyCount = computed(() => ctx.value?.counts?.history || 0);
  const pendingHasMore = computed(() => Boolean(ctx.value?.pages?.pending?.has_more));
  const decidedHasMore = computed(() => Boolean(ctx.value?.pages?.decided?.has_more));
  const supervisorName = computed(() => ctx.value?.supervisor?.full_name || "");

  const planByName = (name) => plans.value.find((p) => p.name === name) || null;

  async function load() {
    if (!ctx.value) loadState.value = "loading";
    const ticket = seq.next();
    try {
      const res = await getSupervisorContext();
      /* The 45 s poll, the realtime handler and the manual refresh all land here, so a slow
         response can finish after a newer one. Only the latest ticket may write. */
      if (!seq.isCurrent(ticket)) return;
      ctx.value = res;
      const contextNames = new Set((res.plans || []).map((plan) => plan.name));
      targetedPlans.value = targetedPlans.value.filter((plan) => !contextNames.has(plan.name));
      loadState.value = "ready";
      loadError.value = "";
    } catch (e) {
      if (!seq.isCurrent(ticket)) return;
      loadState.value = "error";
      loadError.value = resourceErrorMessage(e, "list.loadError");
    }
  }

  async function ensurePlan(name, { refresh = false } = {}) {
    if (!name) return { ok: false };
    const existing = planByName(name);
    if (existing && !refresh) {
      targetLoadState.value = "ready";
      targetLoadError.value = "";
      return { ok: true, plan: existing };
    }

    const ticket = targetSeq.next();
    targetLoadState.value = "loading";
    targetLoadError.value = "";
    try {
      const res = await getSupervisorPlan(name);
      if (!targetSeq.isCurrent(ticket)) return { ok: false };
      const plan = res?.plan;
      if (!plan) throw new Error("Missing plan payload");
      targetedPlans.value = mergePlanPage(targetedPlans.value, [plan]);
      targetLoadState.value = "ready";
      return { ok: true, plan };
    } catch (e) {
      if (!targetSeq.isCurrent(ticket)) return { ok: false };
      targetLoadState.value = "error";
      targetLoadError.value = resourceErrorMessage(e, "list.loadError");
      return { ok: false, message: targetLoadError.value };
    }
  }

  async function loadMore(lane) {
    if (!ctx.value || laneBusy.value[lane]) return { ok: false };
    laneBusy.value = { ...laneBusy.value, [lane]: true };
    const start = loadedForLane(ctx.value.plans || [], lane);
    try {
      const page = await getSupervisorPlans(lane, start);
      ctx.value = {
        ...ctx.value,
        plans: mergePlanPage(ctx.value.plans || [], page.plans || []),
        pages: { ...ctx.value.pages, [lane]: page },
      };
      return { ok: true };
    } catch (e) {
      return { ok: false, message: resourceErrorMessage(e, "list.loadError") };
    } finally {
      laneBusy.value = { ...laneBusy.value, [lane]: false };
    }
  }

  /* Both writers return the outcome rather than raising a toast themselves: the caller owns the
     words, and the verb on the toast has to match the verb on the button that was pressed. */
  async function approve(name) {
    if (!name || busy.value) return { ok: false };
    busy.value = true;
    try {
      await approveRoutePlan(name);
      await load();
      // A decision can move a plan out of the first loaded page. Re-fetch the selected
      // record unconditionally so its deep link never disappears after the write.
      await ensurePlan(name, { refresh: true });
      return { ok: true };
    } catch (e) {
      return { ok: false, message: resourceErrorMessage(e, "approval.actionError") };
    } finally {
      busy.value = false;
    }
  }

  async function reject(name, reason) {
    if (!name || busy.value) return { ok: false };
    busy.value = true;
    try {
      await rejectRoutePlan(name, reason);
      await load();
      await ensurePlan(name, { refresh: true });
      return { ok: true };
    } catch (e) {
      return { ok: false, message: resourceErrorMessage(e, "approval.actionError") };
    } finally {
      busy.value = false;
    }
  }

  const store = {
    ctx,
    loadState,
    loadError,
    busy,
    laneBusy,
    targetLoadState,
    targetLoadError,
    plans,
    pendingPlans,
    activePlans,
    historyPlans,
    pendingCount,
    decidedCount,
    activeCount,
    historyCount,
    pendingHasMore,
    decidedHasMore,
    supervisorName,
    planByName,
    load,
    ensurePlan,
    loadMore,
    approve,
    reject,
  };
  provide(PLANS, store);
  return store;
}

export function usePlans() {
  const store = inject(PLANS, null);
  if (!store) throw new Error("usePlans() outside a component tree that created the store");
  return store;
}
