// Copyright (c) 2026, afmcoltd
import { createI18n } from "@shared/i18n";

import en from "./en.js";
import ar from "./ar.js";
import enums from "./enums.js";

const STORAGE_KEY = "salis_portal_lang";

export const SUPPORTED = ["en", "ar"];

const messages = { en, ar };

export const ISSUE_CATEGORIES = Object.keys(enums.en.issueCategory);
export const ISSUE_PRIORITIES = Object.keys(enums.en.issuePriority);

const { lang, dir, translate, setLang, resourceErrorMessage } = createI18n({
  messages,
  storageKey: STORAGE_KEY,
  supported: SUPPORTED,
});

export { translate, setLang, resourceErrorMessage };

const INTL_LOCALE = { ar: "ar-SA-u-ca-gregory-nu-latn", en: "en-US" };

function intlLocale() {
  return INTL_LOCALE[lang.value] || "en-US";
}

export function fmtNumber(value, opts) {
  if (value == null || value === "" || isNaN(Number(value))) return value;
  return new Intl.NumberFormat(intlLocale(), opts).format(Number(value));
}

export function fmtTime(value) {
  if (!value) return "";
  const m = String(value).match(/(\d{1,2}):(\d{2})/);
  if (!m) return String(value);
  const d = new Date();
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  return new Intl.DateTimeFormat(intlLocale(), { hour: "2-digit", minute: "2-digit" }).format(d);
}

export function fmtDate(value) {
  if (!value) return "";
  const d = new Date(String(value) + "T00:00:00");
  if (isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(intlLocale(), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
}

export function fmtTodayDate() {
  return new Intl.DateTimeFormat(intlLocale(), {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
}

export function translateEnum(namespace, value) {
  if (value == null || value === "") return value;
  const ns = (enums[lang.value] || {})[namespace] || (enums.en || {})[namespace];
  return (ns && ns[value]) != null ? ns[value] : value;
}

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    te: (namespace, value) => translateEnum(namespace, value),
    n: fmtNumber,
    fmtTime,
    fmtDate,
    fmtTodayDate,
    lang,
    dir,
    setLang,
  };
}
