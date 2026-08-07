// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

export const toasts = ref([]);

let seq = 0;

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

export function clearToasts() {
  toasts.value = [];
}
