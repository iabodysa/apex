// Copyright (c) 2026, AFMCO and contributors
// Pure, framework-free helpers for the Fleet OS board — no Vue reactivity and no
// i18n (t). The t-bound display formatters live in useFleetFormat.js; anything
// that is a plain data/date/string transform belongs here so it stays testable
// and shareable across the composables.

// Status badge meta (his SB map): static class + icon; the label is resolved
// reactively via t() in useFleetFormat (follows the language toggle).
export const SB = {
  assigned: { cls: "sb-assigned", ic: "lock" },
  available: { cls: "sb-available", ic: "circle-dot" },
  workshop: { cls: "sb-workshop", ic: "wrench" },
  stopped: { cls: "sb-stopped", ic: "circle-pause" },
  stolen: { cls: "sb-stolen", ic: "shield-alert" },
};

// Compliance flag window: flag a vehicle whose next document expires within N days.
export const EXPIRY_FLAG_DAYS = 7;

export const statusKey = (s) => (SB[s] ? s : "stopped");
// Sheet-type icon name (car vs motorcycle).
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

// Merged timeline (his buildHistoryPanel — driver spells only; the event log
// was a client-only construct, so this renders the live assignment history).
export function historyItems(v) {
  return v.history
    .map((h) => ({ d: h, date: h.date_receive || "0000" }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

// Normalize a fetched vehicle to the shape his render code reads (defends the
// client-only fields the live API leaves empty/null).
export function normalize(v) {
  if (!Array.isArray(v.damages)) v.damages = [];
  if (!Array.isArray(v.accidents)) v.accidents = [];
  if (v.stolen_info === undefined) v.stolen_info = null;
  if (!Array.isArray(v.history)) v.history = [];
  return v;
}

// Frappe surfaces thrown errors as a JSON-encoded _server_messages array; pull
// the human message out of whatever shape arrived.
export function serverMsg(e) {
  let raw = (e && e.message) || String(e || "");
  try {
    const parsed = JSON.parse(raw);
    const arr = Array.isArray(parsed) ? parsed : [parsed];
    const msgs = arr.map((m) => {
      try {
        const o = typeof m === "string" ? JSON.parse(m) : m;
        return o.message || o;
      } catch (_) {
        return m;
      }
    });
    raw = msgs.join(" — ");
  } catch (_) {
    /* not JSON — use as-is */
  }
  return String(raw).replace(/<[^>]*>/g, "").trim();
}
