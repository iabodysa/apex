// Copyright (c) 2026, afmcoltd

export function loadedForLane(plans, lane) {
  return plans.filter((plan) =>
    lane === "pending" ? plan.approval === "Pending" : plan.approval !== "Pending",
  ).length;
}

export function mergePlanPage(existing, incoming) {
  const positions = new Map(existing.map((plan, index) => [plan.name, index]));
  const merged = [...existing];

  for (const plan of incoming) {
    const index = positions.get(plan.name);
    if (index === undefined) {
      positions.set(plan.name, merged.length);
      merged.push(plan);
    } else {
      merged[index] = plan;
    }
  }
  return merged;
}

export function pagedSubsetState({ loadState, itemCount, hasMore }) {
  if (loadState === "loading") return "loading";
  if (loadState === "error") return "error";
  return itemCount > 0 || hasMore ? "ready" : "empty";
}
