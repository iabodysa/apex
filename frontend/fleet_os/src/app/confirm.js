// Copyright (c) 2026, afmcoltd
import { inject, provide, reactive } from "vue";

const CONFIRM = Symbol("apex.fleet-os.confirm");

/* One confirmation surface for the board, awaited by the caller.
 *
 * frappe-ui's `confirmDialog()` was the first choice and is not used: its confirm button label
 * is fixed to the English word "Confirm" (ConfirmDialog.vue) with no prop to change it, and an
 * English button on an Arabic screen is a defect, not a fallback. The library's `Dialog` — the
 * component underneath it — takes localized action labels, and that is what App.vue renders
 * against the state below. It brings the focus trap, the Escape key and the portal with it, so
 * nothing here is hand-rolled except the promise. */
export function provideConfirm() {
  const state = reactive({
    open: false,
    title: "",
    message: "",
    okLabel: "",
    theme: "gray",
  });
  let resolver = null;

  function ask({ title, message, okLabel, theme = "gray" }) {
    state.title = title;
    state.message = message;
    state.okLabel = okLabel;
    state.theme = theme;
    state.open = true;
    return new Promise((resolve) => {
      resolver = resolve;
    });
  }

  function settle(answer) {
    state.open = false;
    if (!resolver) return;
    resolver(answer);
    resolver = null;
  }

  const api = { state, ask, settle };
  provide(CONFIRM, api);
  return api;
}

export function useConfirm() {
  const api = inject(CONFIRM, null);
  if (!api) throw new Error("useConfirm() outside a component tree that provided it");
  return api;
}
