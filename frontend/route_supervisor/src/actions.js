// Copyright (c) 2026, afmcoltd
import { inject, provide } from "vue";

const ACTIONS = Symbol("apex.route-supervisor.actions");

/* The decisions live at the root because both the queue and the open plan raise them, and the
   rejection dialog must not move the selection: deciding a card the supervisor had not opened
   used to throw him out of the queue he was working through. */
export function provideActions(actions) {
  provide(ACTIONS, actions);
  return actions;
}

export function useActions() {
  const actions = inject(ACTIONS, null);
  if (!actions) throw new Error("useActions() outside a component tree that provided them");
  return actions;
}
