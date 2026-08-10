// Copyright (c) 2026, afmcoltd
import { inject, provide, reactive } from "vue";

const CONFIRM = Symbol("apex.fleet-os.confirm");

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
