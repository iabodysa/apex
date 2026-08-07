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
export const initials = (d) => (d ? (d.name_ar || d.name_en || "") : "").slice(0, 2);
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
  return v.history.reduce((s, h) => {
    if (!h.date_receive) return s;
    const d1 = new Date(h.date_receive);
    const d2 = h.date_deliver ? new Date(h.date_deliver) : new Date();
    return s + Math.max(0, Math.round((d2 - d1) / 86400000));
  }, 0);
}

export function historyItems(v) {
  return v.history
    .map((h) => ({ d: h, date: h.date_receive || "0000" }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function normalize(v) {
  if (!Array.isArray(v.damages)) v.damages = [];
  if (!Array.isArray(v.accidents)) v.accidents = [];
  if (v.stolen_info === undefined) v.stolen_info = null;
  if (!Array.isArray(v.history)) v.history = [];
  return v;
}
