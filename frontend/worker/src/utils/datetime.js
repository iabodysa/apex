// Copyright (c) 2026, afmcoltd
import { useI18n } from "../i18n";

const { lang } = useI18n();

function localeFor(code) {
  return code === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-US";
}

function parse(value) {
  if (value == null || value === "") return null;
  const s = String(value).trim();
  if (!s) return null;

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

  m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (m) {
    return new Date(2000, 0, 1, Number(m[1]), Number(m[2]), Number(m[3] || 0));
  }

  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

const DATE_OPTS = { day: "numeric", month: "short", year: "numeric" };
const TIME_OPTS = { hour: "numeric", minute: "2-digit", hour12: true };

export function formatDate(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), DATE_OPTS).format(d);
}

export function formatTime(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), TIME_OPTS).format(d);
}

export function formatDateTime(value) {
  const d = parse(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(localeFor(lang.value), {
    ...DATE_OPTS,
    ...TIME_OPTS,
  }).format(d);
}
