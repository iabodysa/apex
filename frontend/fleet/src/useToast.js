// Copyright (c) 2026, AFMCO and contributors
// Transient toast for action feedback (his showToast). Auto-hides after 3.5s;
// re-firing resets the timer so the latest message wins.
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
