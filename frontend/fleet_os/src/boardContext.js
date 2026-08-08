// Copyright (c) 2026, afmcoltd
import { inject, provide } from "vue";

const BOARD = Symbol("apex.fleet-os.board");

/* The board is one screen with one context, so its regions inject it rather than being handed
   thirty props each. The old components took the whole store as a prop list, which meant every
   new piece of state had to be threaded through three files before it reached the markup. */
export function provideBoardContext(ctx) {
  provide(BOARD, ctx);
  return ctx;
}

export function useBoardContext() {
  const ctx = inject(BOARD, null);
  if (!ctx) throw new Error("useBoardContext() outside the board");
  return ctx;
}
