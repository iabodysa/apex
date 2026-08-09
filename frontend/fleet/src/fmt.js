// Copyright (c) 2026, afmcoltd

/* Arabic with Latin digits: a plate, an odometer and a litre count are read aloud as numerals
   on the yard, and Eastern Arabic digits made people re-read them. */
const AR_LOCALE = "ar-SA-u-nu-latn";

export const localeFor = (lang) => (lang === "ar" ? AR_LOCALE : "en-US");

export function formatInt(value, lang, fallback = "—") {
  if (value == null) return fallback;
  return new Intl.NumberFormat(localeFor(lang)).format(value);
}

export function formatToday(lang) {
  return new Intl.DateTimeFormat(localeFor(lang), {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
}

export function formatDate(value, lang, fallback = "—") {
  if (!value) return fallback;
  const source = String(value);
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(source) ? `${source}T00:00:00` : source);
  if (Number.isNaN(date.getTime())) return source;
  return new Intl.DateTimeFormat(localeFor(lang), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function formatTime(value, lang, fallback = "—") {
  if (!value) return fallback;
  const match = String(value).match(/^(\d{1,2}):(\d{2})/);
  if (!match) return String(value);
  const date = new Date(2000, 0, 1, Number(match[1]), Number(match[2]));
  return new Intl.DateTimeFormat(localeFor(lang), {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
