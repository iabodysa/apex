// Copyright (c) 2026, afmcoltd
import { ref } from "vue";
import { createI18n } from "@shared/i18n";

import en from "./en.js";
import ar from "./ar.js";
import ur from "./ur.js";
import hi from "./hi.js";
import bn from "./bn.js";

const STORAGE_KEY = "masar_portal_lang";

export const SUPPORTED = ["en", "ar", "ur", "hi", "bn"];

const RTL_LANGS = ["ar", "ur"];

export const LANG_NAMES = {
  en: "English",
  ar: "العربية",
  ur: "اردو",
  hi: "हिन्दी",
  bn: "বাংলা",
};

const messages = { en, ar, ur, hi, bn };

const enumLabels = ref({});

export function setEnumLabels(code, labels) {
  if (!SUPPORTED.includes(code)) return;
  enumLabels.value = { ...enumLabels.value, [code]: labels || {} };
}

const { lang, dir, translate, setLang, resourceErrorMessage } = createI18n({
  messages,
  storageKey: STORAGE_KEY,
  supported: SUPPORTED,
  rtlLangs: RTL_LANGS,
});

export { translate, setLang, resourceErrorMessage };

export function translateEnum(namespace, value) {
  if (value == null || value === "") return value;
  const map = (enumLabels.value[lang.value] || {})[namespace];
  return (map && map[value]) || value;
}

export function useI18n() {
  return {
    t: (key, params) => translate(key, params),
    tEnum: (namespace, value) => translateEnum(namespace, value),
    lang,
    dir,
    setLang,
  };
}
