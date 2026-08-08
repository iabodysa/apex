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
