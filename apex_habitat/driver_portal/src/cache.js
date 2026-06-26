// Offline cache for read-only "today"/route payloads. The driver portal is used in
// the field where the network drops mid-shift; this lets a screen render the LAST
// successful response (labelled stale) instead of a bare error. Writes are never
// cached — only safe identity-scoped reads, keyed per endpoint.
import { ref } from "vue";

const PREFIX = "salis_portal_cache:";

// Reactive online flag, kept in sync with the browser's connectivity events so a
// banner can show/hide without polling. Starts from navigator.onLine.
export const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
if (typeof window !== "undefined") {
  window.addEventListener("online", () => (online.value = true));
  window.addEventListener("offline", () => (online.value = false));
}

// Persist a successful payload under `key` with a timestamp, so a later read can
// label how old it is. Best-effort: a full/blocked localStorage is a silent no-op.
export function cacheSet(key, data) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify({ at: Date.now(), data }));
  } catch (e) {
    // storage full or unavailable (private mode) — degrade to no cache
  }
}

// The last cached { data, at } for `key`, or null when nothing is stored / parse fails.
export function cacheGet(key) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && "data" in parsed) return parsed;
  } catch (e) {
    // corrupt entry — treat as no cache
  }
  return null;
}
