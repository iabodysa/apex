// Copyright (c) 2026, afmcoltd

export const SB = {
  assigned: { cls: "sb-assigned", ic: "lock" },
  available: { cls: "sb-available", ic: "circle-dot" },
  workshop: { cls: "sb-workshop", ic: "wrench" },
  stopped: { cls: "sb-stopped", ic: "circle-pause" },
  stolen: { cls: "sb-stolen", ic: "shield-alert" },
};

export const EXPIRY_FLAG_DAYS = 7;

export const statusKey = (s) => (SB[s] ? s : "stopped");
export const icon = (v) => (v.sheet === "CAR" ? "car" : "bike");
export const initials = (d) => (d ? d.name_ar || d.name_en || "" : "").slice(0, 2);
export const trim = (x) => (x || "").toString().trim();

export function normalizeReaderErrors(errors) {
  return (Array.isArray(errors) ? errors : [])
    .map((item) => {
      if (typeof item === "string") return trim(item);
      if (!item || typeof item !== "object") return "";
      return trim(item.error) || trim(item.reader);
    })
    .filter(Boolean);
}

export const createStopForm = (nextStatus = "available") => ({
  reason: "",
  notes: "",
  nextStatus,
});

export const createTheftForm = () => ({
  police: "",
  location: "",
});

export const canAssignVehicle = (vehicle) => vehicle?.vehicle_status === "available";

export const canStopVehicle = (vehicle) =>
  Boolean(vehicle && ["assigned", "available"].includes(vehicle.vehicle_status));

export const canSendToWorkshop = (vehicle) =>
  Boolean(
    vehicle &&
    !vehicle.current_driver &&
    ["available", "stopped"].includes(vehicle.vehicle_status),
  );

export const canChooseVehicleStatus = (vehicle, target) => {
  const current = vehicle?.vehicle_status;
  if (!current || !target || target === current || vehicle.current_driver) return false;
  if (["workshop", "stolen"].includes(current)) return false;
  if (target === "assigned") return current === "available";
  return (
    ["available", "stopped"].includes(current) &&
    ["available", "workshop", "stopped", "stolen"].includes(target)
  );
};

export const vehicleStatusTone = (status) => ({
  assigned: "success",
  available: "info",
  workshop: "warning",
  stopped: "neutral",
  stolen: "danger",
})[status] || "neutral";

export function normalizeBulkResult(result) {
  const source = result || {};
  const rows = (Array.isArray(source.results) ? source.results : []).map((row) => ({
    plate: trim(row?.plate),
    ok: row?.ok === true,
    error: trim(row?.error),
  }));
  return {
    succeeded: Number(source.succeeded) || 0,
    failed: Number(source.failed) || 0,
    rows,
  };
}

export function today() {
  return new Date().toISOString().split("T")[0];
}

export function calcTotalDaysNum(v) {
  if (!v.history.length) return 0;
  const first = v.history[0].date_receive;
  if (!first) return 0;
  return Math.max(0, Math.round((new Date() - new Date(first)) / 86400000));
}

export function calcActiveDaysNum(v) {
  return v.history.reduce((sum, h) => {
    if (!h.date_receive) return sum;
    const from = new Date(h.date_receive);
    const to = h.date_deliver ? new Date(h.date_deliver) : new Date();
    return sum + Math.max(0, Math.round((to - from) / 86400000));
  }, 0);
}

export function historyItems(v) {
  return v.history
    .map((h) => ({ d: h, date: h.date_receive || "0000" }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function hasOpenIncident(v) {
  return (
    (v.damages || []).some((d) => d.status !== "completed") ||
    (v.accidents || []).some((a) => a.status !== "closed")
  );
}

export function normalize(v) {
  if (!Array.isArray(v.damages)) v.damages = [];
  if (!Array.isArray(v.accidents)) v.accidents = [];
  if (v.stolen_info === undefined) v.stolen_info = null;
  if (!Array.isArray(v.history)) v.history = [];
  return v;
}
