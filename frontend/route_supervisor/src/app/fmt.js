// Copyright (c) 2026, afmcoltd

export function ageLabel(seconds, t) {
  if (seconds == null) return t("map.justNow");
  const s = Math.max(0, Math.floor(seconds));
  if (s < 45) return t("map.justNow");
  if (s < 3600) return t("time.min", { n: Math.round(s / 60) });
  return t("time.hour", { n: Math.round(s / 3600) });
}

export function agoLabel(value, lang) {
  /* Intl.RelativeTimeFormat is the platform's own, and it carries the Arabic dual and the
     plural rules that a {n} template cannot. A Frappe datetime is "YYYY-MM-DD HH:MM:SS" in
     the site's timezone, which Date only parses with the T separator. */
  if (!value) return "";
  const then = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(then.getTime())) return String(value);

  const seconds = Math.round((then.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const rtf = new Intl.RelativeTimeFormat(lang || "ar", { numeric: "auto" });

  if (abs < 60) return rtf.format(seconds, "second");
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 2592000) return rtf.format(Math.round(seconds / 86400), "day");
  if (abs < 31536000) return rtf.format(Math.round(seconds / 2592000), "month");
  return rtf.format(Math.round(seconds / 31536000), "year");
}

export function pct(boarded, expected) {
  if (!expected || expected <= 0) return 0;
  return Math.min(100, Math.round((boarded / expected) * 100));
}

/* A response that started earlier must never land on top of a newer one. Each caller takes a
   ticket before it fetches and only writes when its ticket is still the latest one issued. */
export function createSequence() {
  let issued = 0;
  return {
    next: () => ++issued,
    isCurrent: (ticket) => ticket === issued,
  };
}
