// Copyright (c) 2026, AFMCO and contributors
// Test fixture standing in for a portal's src/i18n.js (resolved via the `@` alias in
// vitest.config). Gives the shared components a real reactive `lang` + a spy-able
// setLang so LangToggle/BuildingPicker can be mounted in isolation.
import { ref } from "vue";

export const lang = ref("en");
export const dir = ref("ltr");

export function setLang(next) {
  lang.value = next;
  dir.value = next === "ar" ? "rtl" : "ltr";
}

// Echoes the key so assertions can match on the i18n key without a dictionary.
export function useI18n() {
  return {
    t: (key) => key,
    lang,
    dir,
    setLang,
  };
}

export function resourceErrorMessage(_e, fallbackKey = "errors.loadError") {
  return fallbackKey;
}
