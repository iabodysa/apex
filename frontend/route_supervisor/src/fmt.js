// Copyright (c) 2026, AFMCO and contributors
// Small presentation helpers shared by the panels.

// A compact "X ago" label from a seconds count, localized via the portal's t().
export function ageLabel(seconds, t) {
  if (seconds == null) return t("map.justNow");
  const s = Math.max(0, Math.floor(seconds));
  if (s < 45) return t("map.justNow");
  if (s < 3600) return t("time.min", { n: Math.round(s / 60) });
  return t("time.hour", { n: Math.round(s / 3600) });
}

// Clamp a 0..1 ratio to a whole percentage for the progress bar width.
export function pct(boarded, expected) {
  if (!expected || expected <= 0) return 0;
  return Math.min(100, Math.round((boarded / expected) * 100));
}
