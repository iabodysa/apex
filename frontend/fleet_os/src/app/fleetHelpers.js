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

/* The server omits an empty child table rather than sending an empty list, so every consumer
   would otherwise have to guard each one. */
export function normalize(v) {
  if (!Array.isArray(v.damages)) v.damages = [];
  if (!Array.isArray(v.accidents)) v.accidents = [];
  if (v.stolen_info === undefined) v.stolen_info = null;
  if (!Array.isArray(v.history)) v.history = [];
  return v;
}
