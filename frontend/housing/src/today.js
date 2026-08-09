// Copyright (c) 2026, afmcoltd

function number(value) {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function occupancyMetrics(summary) {
  const source = summary || {};
  return {
    total: number(source.total_beds),
    occupied: number(source.occupied),
    available: number(source.available),
    unavailable: number(source.blocked) + number(source.out_of_service),
  };
}

export function pendingArrivals(manifest) {
  const source = manifest || {};
  if (source.pending != null) return number(source.pending);
  return Math.max(0, number(source.total) - number(source.arrived));
}

export function draftCount(draft) {
  return draft && typeof draft === "object" ? Object.keys(draft).length : 0;
}

export function countRoundMarks(draft) {
  if (!draft || typeof draft !== "object") return 0;
  let total = 0;
  for (const tasks of Object.values(draft)) {
    if (!tasks || typeof tasks !== "object") continue;
    total += Object.values(tasks).filter((mark) => mark && mark.verdict).length;
  }
  return total;
}

export function todayPageState({ loading, loaded, failed, total }) {
  if (loading && loaded === 0) return "loading";
  if (total > 0 && loaded === 0 && failed === total) return "error";
  return "ready";
}
