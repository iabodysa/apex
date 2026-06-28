// [#t648-make-cache]
// makeCache(prefix) factory shared by driver_portal and worker_portal.
// Each portal's cache.js calls this with its own namespace prefix and
// re-exports the resulting { cacheSet, cacheGet, online } so existing
// per-file imports stay unchanged.
//
// Offline strategy: read-only "today"/route payloads are stored under
// `<prefix><key>` in localStorage with a timestamp, so a screen can render
// the LAST successful response (labelled stale) instead of a bare error
// when the network drops mid-shift. Writes are never cached.

import { ref } from "vue";

export function makeCache(prefix) {
  // Reactive online flag, kept in sync with browser connectivity events so a
  // banner can show/hide without polling. Starts from navigator.onLine.
  const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
  if (typeof window !== "undefined") {
    window.addEventListener("online", () => (online.value = true));
    window.addEventListener("offline", () => (online.value = false));
  }

  // Persist a successful payload under `key` with a timestamp. Best-effort:
  // a full/blocked localStorage is a silent no-op.
  function cacheSet(key, data) {
    try {
      localStorage.setItem(prefix + key, JSON.stringify({ at: Date.now(), data }));
    } catch (e) {
      // storage full or unavailable (private mode) — degrade to no cache
    }
  }

  // The last cached { data, at } for `key`, or null when nothing is stored
  // or the entry cannot be parsed.
  function cacheGet(key) {
    try {
      const raw = localStorage.getItem(prefix + key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && "data" in parsed) return parsed;
    } catch (e) {
      // corrupt entry — treat as no cache
    }
    return null;
  }

  return { online, cacheSet, cacheGet };
}
