// Copyright (c) 2026, AFMCO and contributors
// resourceErrorMessage must never put a raw server sentence on screen: the server
// localizes against frappe.local.lang, not the portal toggle, so its text can be in
// a language the user never chose (and carries the URL + exception class besides).
import { describe, it, expect, beforeEach } from "vitest";
import { createI18n } from "@shared/i18n.js";

const messages = {
  en: {
    errors: {
      loadError: "Couldn't load this section.",
      rateLimited: "Too many requests. Please wait a moment and try again.",
      sessionExpired: "Your session expired. Please refresh the page.",
    },
  },
  ar: {
    errors: {
      loadError: "تعذّر تحميل هذا القسم.",
      rateLimited: "طلبات كثيرة جداً. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى.",
      sessionExpired: "انتهت صلاحية الجلسة. يرجى تحديث الصفحة.",
    },
  },
};

// The exact shape frappe-ui's frappeRequest builds on a failed response: message is
// "<url> <exc_type> <_error_message>" and messages[] carries the server sentence.
function frappeError({ excType = "", status = 500, serverMessage = "" } = {}) {
  const e = new Error(`/api/method/apex.salis.api.masar.get_worker_home ${excType} boom`);
  e.exc_type = excType;
  e.response = { status };
  e.messages = serverMessage ? [serverMessage] : ["Internal Server Error"];
  return e;
}

describe("resourceErrorMessage", () => {
  let i18n;
  beforeEach(() => {
    localStorage.clear();
    i18n = createI18n({ messages, storageKey: "test_lang", defaultLang: "en" });
  });

  for (const [locale, expected] of [
    ["en", messages.en.errors.loadError],
    ["ar", messages.ar.errors.loadError],
  ]) {
    it(`resolves an unmapped exception class to the ${locale} fallback line`, () => {
      i18n.setLang(locale);
      // ValidationError is not one of the two mapped classes, and the server sentence
      // arrives in the WRONG language for this portal — the fallback must win.
      const e = frappeError({
        excType: "ValidationError",
        serverMessage: locale === "ar" ? "Vehicle already has a driver" : "المركبة لديها سائق",
      });
      const msg = i18n.resourceErrorMessage(e, "errors.loadError");
      expect(msg).toBe(expected);
      expect(msg).not.toContain("ValidationError");
      expect(msg).not.toContain("/api/method/");
    });
  }

  it("keeps the mapped rate-limit and session-expired lines translated", () => {
    i18n.setLang("ar");
    expect(i18n.resourceErrorMessage(frappeError({ status: 429 }))).toBe(
      messages.ar.errors.rateLimited,
    );
    expect(i18n.resourceErrorMessage(frappeError({ excType: "CSRFTokenError", status: 417 }))).toBe(
      messages.ar.errors.sessionExpired,
    );
  });

  it("never leaks frappe-ui's untranslated 'Internal Server Error' default", () => {
    i18n.setLang("ar");
    expect(i18n.resourceErrorMessage(frappeError())).toBe(messages.ar.errors.loadError);
  });
});
