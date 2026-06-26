// Transient toast store: a success/error message that auto-dismisses and is
// cleared on route change, replacing the persistent status-note that lingered
// after navigation. One module-level store so any page can push and a single
// <Toast> host (mounted in App.vue) renders the queue.
import { ref } from "vue";

export const toasts = ref([]);

let seq = 0;

// Show a transient toast. `kind` is "ok" | "err" (drives colour); it auto-removes
// after `ttl` ms (a touch longer for errors so they're readable).
export function pushToast(message, kind = "ok", ttl) {
  if (!message) return;
  const id = ++seq;
  const life = ttl ?? (kind === "err" ? 4000 : 2500);
  toasts.value.push({ id, message, kind });
  setTimeout(() => dismissToast(id), life);
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

// Clear everything — called on route change so a success toast never lingers
// onto the next screen.
export function clearToasts() {
  toasts.value = [];
}
