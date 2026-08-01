// Copyright (c) 2026, AFMCO and contributors
// Locale-aware date/time formatting for the worker portal.
//
// The backend (salis/api/masar.py) sends bare strings: dates as "YYYY-MM-DD",
// clock times as "HH:MM:SS", and datetimes as "YYYY-MM-DD HH:MM:SS". We render
// them with the native Intl.DateTimeFormat so an Arabic worker sees a localized
// month and 12-hour time and an English one the equivalent ("20 Jun 2026" /
// "6:00 AM"); the localized forms come from Intl, never from a literal here.
//
// Reactivity: these helpers read `lang.value` (the same reactive ref t() uses),
// so a render that calls them re-runs when the user toggles the language.
import { useI18n } from "../i18n";

// useI18n() returns the singleton `lang` ref — reading `.value` inside a render
// tracks it as a dependency, exactly as t() does.
const { lang } = useI18n();

// ar/en → a BCP-47 locale. Force the Gregorian calendar and Latin digits so the
// output matches the backend's Gregorian dates and stays digit-stable (ar-SA
// would otherwise default to the Islamic calendar / Arabic-Indic digits).
function localeFor(code) {
  return code === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-US";
}

// Parse a backend string into a Date without timezone surprises.
// `new Date("2026-06-20")` is parsed as UTC midnight (can shift a day in a
// negative-offset zone) and "YYYY-MM-DD HH:MM:SS" is rejected by Safari — so we
// pull the parts out by regex and build a local-time Date explicitly.
function parse(value) {
  if (value == null || value === "") return null;
  const s = String(value).trim();
  if (!s) return null;

  // Date or datetime: YYYY-MM-DD optionally followed by HH:MM(:SS).
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (m) {
    return new Date(
      Number(m[1]),
      Number(m[2]) - 1,
      Number(m[3]),
      Number(m[4] || 0),
      Number(m[5] || 0),
      Number(m[6] || 0),
    );
  }

  // Time-only: HH:MM(:SS). Anchor to an arbitrary date — only the time is shown.
  m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (m) {
    return new Date(2000, 0, 1, Number(m[1]), Number(m[2]), Number(m[3] || 0));
  }

  // Last resort: let the engine try (ISO strings with offsets, etc.).
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

const DATE_OPTS = { day: "numeric", month: "short", year: "numeric" };
const TIME_OPTS = { hour: "numeric", minute: "2-digit", hour12: true };

// Localized date, e.g. "20 Jun 2026" under en. "" for null/empty.
export function formatDate(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), DATE_OPTS).format(d);
}

// Localized 12-hour time, e.g. "6:00 AM" under en. "" for null/empty.
export function formatTime(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), TIME_OPTS).format(d);
}

// Localized date + 12-hour time, e.g. "20 Jun 2026, 6:00 AM" under en. "" for null/empty.
export function formatDateTime(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), {
    ...DATE_OPTS,
    ...TIME_OPTS,
  }).format(d);
}
