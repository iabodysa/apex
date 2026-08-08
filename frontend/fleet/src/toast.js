// Copyright (c) 2026, afmcoltd
import { inject, provide } from "vue";

import { useToast } from "@shared/useToast.js";

const TOAST = Symbol("apex.fleet.toast");

/* One toast surface for the whole page, created at the root. A screen that mounts its own ends
   up with a second surface that outlives the route change it was raised on. */
export function provideToast() {
  const api = useToast();
  provide(TOAST, api);
  return api;
}

export function useAppToast() {
  const api = inject(TOAST, null);
  if (!api) throw new Error("useAppToast() outside a component tree that provided it");
  return api;
}
