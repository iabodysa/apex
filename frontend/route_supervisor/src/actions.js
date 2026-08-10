// Copyright (c) 2026, afmcoltd
import { inject, provide } from "vue";

const ACTIONS = Symbol("apex.route-supervisor.actions");

export function provideActions(actions) {
  provide(ACTIONS, actions);
  return actions;
}

export function useActions() {
  const actions = inject(ACTIONS, null);
  if (!actions) throw new Error("useActions() outside a component tree that provided them");
  return actions;
}
