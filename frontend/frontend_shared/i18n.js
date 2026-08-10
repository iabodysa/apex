// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";

import { SHARED_MESSAGES } from "./sharedMessages.js";

export function createI18n({
  messages,
  storageKey,
  supported = ["en", "ar"],
  defaultLang = "ar",
  rtlLangs = ["ar"],
}) {
  function detectInitial() {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved && supported.includes(saved)) return saved;
    } catch (e) {
    }
    return defaultLang;
  }

  const lang = ref(detectInitial());

  function resolve(source, locale, key) {
    return key.split(".").reduce((o, part) => (o == null ? undefined : o[part]), source[locale]);
  }

  function lookup(locale, key) {
    const own = resolve(messages, locale, key);
    if (own != null) return own;
    return resolve(SHARED_MESSAGES, locale, key);
  }

  function interpolate(str, params) {
    if (!params) return str;
    return String(str).replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
  }

  function translate(key, params) {
    const val = lookup(lang.value, key);
    if (val != null && typeof val !== "object") return interpolate(val, params);
    const fallback = lookup("en", key);
    return interpolate(fallback != null && typeof fallback !== "object" ? fallback : key, params);
  }

  function setLang(next) {
    if (!supported.includes(next)) return;
    lang.value = next;
    try {
      localStorage.setItem(storageKey, next);
    } catch (e) {
    }
  }

  const dir = computed(() => (rtlLangs.includes(lang.value) ? "rtl" : "ltr"));

  function resourceErrorMessage(e, fallbackKey = "errors.loadError") {
    if (!e) return translate(fallbackKey);
    const status = e.response?.status;
    const excType = e.exc_type || "";
    if (status === 429 || excType === "TooManyRequestsError") {
      return translate("errors.rateLimited");
    }
    if (excType.includes("CSRFTokenError") || excType.includes("Authorization")) {
      return translate("errors.sessionExpired");
    }
    /* A record the server has never heard of is the one failure whose cause a reader can
       act on, and it looks identical to every other failure unless it is named. It happens
       to anyone carrying a saved choice from a site that no longer holds it. */
    if (excType.includes("DoesNotExist") || status === 404) {
      return translate("errors.gone");
    }
    if (excType.includes("PermissionError")) {
      return translate("errors.notAllowed");
    }
    return translate(fallbackKey);
  }

  return { lang, dir, lookup, interpolate, translate, setLang, resourceErrorMessage };
}
