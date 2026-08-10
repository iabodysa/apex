// Copyright (c) 2026, afmcoltd
import { inject, provide } from "vue";

const BOARD = Symbol("apex.fleet-os.board");

export function provideBoardContext(ctx) {
  provide(BOARD, ctx);
  return ctx;
}

export function useBoardContext() {
  const ctx = inject(BOARD, null);
  if (!ctx) throw new Error("useBoardContext() outside the board");
  return ctx;
}
