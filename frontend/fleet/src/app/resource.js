// Copyright (c) 2026, afmcoltd
import { computed, reactive } from "vue";

import { resourceErrorMessage } from "@/i18n";

/* One resource = one reader, its own state and its own error.
 *
 * The screens used to share a single `loadError` boolean across three parallel reads, so a
 * failure in any one of them made the other two claim an error they never had. Splitting the
 * state per reader is what lets a screen say "your vehicle could not be loaded" while the trip
 * list beside it is fine.
 *
 * frappe-ui's own `createResource` was the first choice and is not used here: it assigns the
 * response to `data` unconditionally, with no request sequence, so two overlapping fetches can
 * land oldest-last. The ticket below is the whole reason this wrapper exists. */
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
