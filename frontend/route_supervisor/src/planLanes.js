// Copyright (c) 2026, afmcoltd

export function laneForPlan(plan) {
  if (plan.approval === "Pending") return "pending";
  if (
    plan.approval === "Rejected" ||
    ["Completed", "Cancelled"].includes(plan.trip?.status)
  ) {
    return "history";
  }
  return plan.approval === "Approved" ? "active" : "history";
}

export const isPendingPlan = (plan) => laneForPlan(plan) === "pending";
export const isHistoryPlan = (plan) => laneForPlan(plan) === "history";
export const isActivePlan = (plan) => laneForPlan(plan) === "active";
