// Copyright (c) 2026, afmcoltd

import { ref } from "vue";

export function makeCache(prefix) {
  const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
  if (typeof window !== "undefined") {
    window.addEventListener("online", () => (online.value = true));
    window.addEventListener("offline", () => (online.value = false));
  }

  function cacheSet(key, data) {
    try {
      localStorage.setItem(prefix + key, JSON.stringify({ at: Date.now(), data }));
    } catch (e) {
    }
  }

  function cacheGet(key) {
    try {
      const raw = localStorage.getItem(prefix + key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && "data" in parsed) return parsed;
    } catch (e) {
    }
    return null;
  }

  return { online, cacheSet, cacheGet };
}
