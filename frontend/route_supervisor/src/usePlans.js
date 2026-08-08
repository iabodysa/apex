// Copyright (c) 2026, afmcoltd
import { computed, inject, provide, ref } from "vue";

import { approveRoutePlan, getSupervisorContext, rejectRoutePlan } from "./api.js";
import { createSequence } from "./fmt.js";
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
  const seq = createSequence();

  const plans = computed(() => ctx.value?.plans || []);
  const pendingPlans = computed(() => plans.value.filter((p) => p.approval === "Pending"));
  const pendingCount = computed(() => ctx.value?.counts?.pending || 0);
  const totalCount = computed(() => ctx.value?.counts?.total || 0);
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
      loadState.value = "ready";
      loadError.value = "";
    } catch (e) {
      if (!seq.isCurrent(ticket)) return;
      loadState.value = "error";
      loadError.value = resourceErrorMessage(e, "list.loadError");
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
    plans,
    pendingPlans,
    pendingCount,
    totalCount,
    supervisorName,
    planByName,
    load,
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
