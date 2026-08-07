// Copyright (c) 2026, afmcoltd

export function ageLabel(seconds, t) {
  if (seconds == null) return t("map.justNow");
  const s = Math.max(0, Math.floor(seconds));
  if (s < 45) return t("map.justNow");
  if (s < 3600) return t("time.min", { n: Math.round(s / 60) });
  return t("time.hour", { n: Math.round(s / 3600) });
}

export function pct(boarded, expected) {
  if (!expected || expected <= 0) return 0;
  return Math.min(100, Math.round((boarded / expected) * 100));
}
