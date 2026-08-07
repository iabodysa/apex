// Copyright (c) 2026, AFMCO and contributors
//
// Keep <html dir> and <html lang> in sync with the chosen language, for every portal.
//
// WATCH THE LANGUAGE, NEVER THE DIRECTION. Two languages can share a direction — ar and
// ur are both rtl — so a dir-keyed watcher never fires on ar -> ur and the page keeps
// announcing the old language. Deriving lang from direction is the same bug stated
// differently: `dir === "rtl" ? "ar" : "en"` is only ever right for a portal with exactly
// two languages, and silently wrong the day it gains a third.
//
// This is not cosmetic. @shared/call reads <html lang> and stamps `_lang` on EVERY
// request every portal makes, so the attribute decides the language the server answers
// and refuses in, and a screen reader announces.

import { watch } from "vue";

export function useDocumentLanguage(lang, dir) {
  watch(
    lang,
    (value) => {
      document.documentElement.setAttribute("dir", dir.value);
      document.documentElement.setAttribute("lang", value);
    },
    { immediate: true },
  );
}
