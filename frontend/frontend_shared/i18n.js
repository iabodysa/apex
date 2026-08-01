// Copyright (c) 2026, AFMCO and contributors
// [#shared-i18n]
// createI18n(config) builds the reactive translate / setLang / dir machinery
// shared by every *_portal SPA. Each portal supplies only its own `messages`
// dictionary plus a little config and re-exports the returned members, so no
// portal re-implements the lookup / interpolate / language-persistence layer.
//
// Portal-specific pieces that genuinely differ (translateEnum strategies,
// number/date formatting, LANG_NAMES, server-driven enum labels) stay in the
// portal's i18n.js and build on the primitives this factory returns
// (`lang`, `lookup`, `interpolate`).
import { computed, ref } from "vue";

// config:
//   messages     — { [locale]: nested-object } dictionary (required)
//   storageKey   — localStorage key for the persisted language (required)
//   supported    — allowed locale codes (default ["en", "ar"])
//   defaultLang  — fallback when nothing valid is stored (default "ar")
//   rtlLangs     — locales that render right-to-left (default ["ar"])
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
      /* storage blocked — fall through to default */
    }
    return defaultLang;
  }

  const lang = ref(detectInitial());

  // Resolve a dotted key ("errors.loadFailed") against one locale's messages.
  function lookup(locale, key) {
    return key.split(".").reduce((o, part) => (o == null ? undefined : o[part]), messages[locale]);
  }

  // Fill {name} placeholders from params; leaves unknown placeholders intact.
  function interpolate(str, params) {
    if (!params) return str;
    return String(str).replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
  }

  // Active-locale value, falling back to English then to the raw key (so a
  // missing translation degrades to English, never blanks). Guards against a
  // key that resolves to a namespace object rather than a leaf string.
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
      /* storage blocked — keep the in-memory choice */
    }
  }

  const dir = computed(() => (rtlLangs.includes(lang.value) ? "rtl" : "ltr"));

  // Map a frappe-ui resource error to a short line in the language the user picked.
  // The server sentence is still never rendered HERE. @shared/call now stamps `_lang`
  // on every request, so frappe.throw(_("…")) does resolve against the page's language
  // — but only for the locales ar.csv covers, while worker offers five, and e.message
  // still carries the request URL and the exception class. A portal that genuinely
  // wants the server's own sentence reads e.messages[0] itself (fleet does); this
  // helper is the safe default, so every path ends in translate().
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
    return translate(fallbackKey);
  }

  return { lang, dir, lookup, interpolate, translate, setLang, resourceErrorMessage };
}
