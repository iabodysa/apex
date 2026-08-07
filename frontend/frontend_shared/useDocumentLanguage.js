// Copyright (c) 2026, afmcoltd

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
