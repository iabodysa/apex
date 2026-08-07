// Copyright (c) 2026, afmcoltd
export const fuelMeta = {
  pending: { cls: "pill-warn", key: "emp.fuel.status.pending" },
  approved: { cls: "pill-ok", key: "emp.fuel.status.approved" },
  completed: { cls: "pill-ok", key: "emp.fuel.status.completed" },
  failed: { cls: "pill-danger", key: "emp.fuel.status.failed" },
  cancelled: { cls: "pill-muted", key: "emp.fuel.status.cancelled" },
};

export function fuelMetaFor(statusKey) {
  return fuelMeta[statusKey] || fuelMeta.pending;
}
