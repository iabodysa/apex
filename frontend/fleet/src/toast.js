// Copyright (c) 2026, afmcoltd
import { toast } from "frappe-ui";
import { inject, provide } from "vue";

const TOAST = Symbol("apex.fleet.toast");
const TOAST_TYPES = {
  green: "success",
  amber: "warning",
  red: "error",
};

/* One toast surface for the whole page, created at the root. A screen that mounts its own ends
   up with a second surface that outlives the route change it was raised on. */
export function provideToast() {
  const api = {
    showToast(message, type = "green") {
      toast.create({
        message,
        type: TOAST_TYPES[type] || "info",
        duration: 3.5,
      });
    },
  };
  provide(TOAST, api);
  return api;
}

export function useAppToast() {
  const api = inject(TOAST, null);
  if (!api) throw new Error("useAppToast() outside a component tree that provided it");
  return api;
}
