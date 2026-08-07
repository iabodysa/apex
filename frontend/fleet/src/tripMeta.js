// Copyright (c) 2026, AFMCO and contributors
// Trip status → pill class + label key. One vocabulary for the home preview
// and the /trips page, so the same status can never wear two colours.
export const tripMeta = {
  planned: { cls: "pill-warn", key: "emp.trips.planned" },
  inProgress: { cls: "pill-ok", key: "emp.trips.inProgress" },
  completed: { cls: "pill-ok", key: "emp.trips.completed" },
};

export function metaFor(status) {
  return tripMeta[status] || tripMeta.planned;
}
