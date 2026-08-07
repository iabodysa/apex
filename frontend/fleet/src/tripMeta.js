// Copyright (c) 2026, afmcoltd
export const tripMeta = {
  planned: { cls: "pill-warn", key: "emp.trips.planned" },
  inProgress: { cls: "pill-ok", key: "emp.trips.inProgress" },
  completed: { cls: "pill-ok", key: "emp.trips.completed" },
};

export function metaFor(status) {
  return tripMeta[status] || tripMeta.planned;
}
