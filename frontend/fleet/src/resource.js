// Copyright (c) 2026, afmcoltd
import { computed, reactive } from "vue";

import { resourceErrorMessage } from "@/i18n";

export function createResource({ fetcher, initial = null, errorKey = "errors.loadError" }) {
  let issued = 0;

  const state = reactive({
    data: initial,
    status: "idle",
    error: "",
  });

  async function reload() {
    if (state.status !== "ready") state.status = "loading";
    const ticket = ++issued;
    try {
      const res = await fetcher();
      if (ticket !== issued) return;
      state.data = res;
      state.status = "ready";
      state.error = "";
    } catch (e) {
      if (ticket !== issued) return;
      state.status = "error";
      state.error = resourceErrorMessage(e, errorKey);
    }
  }

  return {
    state,
    reload,
    loading: computed(() => state.status === "loading"),
    failed: computed(() => state.status === "error"),
  };
}
