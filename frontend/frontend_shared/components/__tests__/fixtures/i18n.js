// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

export const lang = ref("en");
export const dir = ref("ltr");

export function setLang(next) {
  lang.value = next;
  dir.value = next === "ar" ? "rtl" : "ltr";
}

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
