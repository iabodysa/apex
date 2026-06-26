// Offline cache for read-only Masar payloads (transport / accommodation / custody /
// home). Workers open the portal in the field where the network drops; this lets a
// screen render the LAST successful response (labelled stale) instead of a bare
// error. Writes are never cached — only safe token-scoped reads, keyed per endpoint.
// Mirrors the driver portal's cache.js pattern.

const PREFIX = "masar_portal_cache:";

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
