// Copyright (c) 2026, AFMCO and contributors
// [#a281-shared-toast]
// Transient toast for action feedback. Auto-hides after 3.5s; re-firing resets the
// timer so the latest message wins. Each caller gets its own independent state.
//
// Shared because it is the one file in this family with NO portal coupling: it
// imports only `vue`, reads no token, no i18n key and no DOM class — the caller
// owns the markup that renders `toast`. Portals import it by direct path:
//   import { useToast } from "@shared/useToast.js";
import { reactive } from "vue";

export function useToast() {
  const toast = reactive({ msg: "", type: "green", show: false });
  let toastTimer = null;
  function showToast(msg, type = "green") {
    toast.msg = msg;
    toast.type = type;
    toast.show = true;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.show = false), 3500);
  }
  return { toast, showToast };
}
