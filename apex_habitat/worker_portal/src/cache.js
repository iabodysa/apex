// [#t648-make-cache]
// Offline cache for read-only Masar payloads (transport / accommodation /
// custody / home). Workers open the portal in the field where the network
// drops; this lets a screen render the LAST successful response (labelled
// stale) instead of a bare error. Writes are never cached — only safe
// token-scoped reads, keyed per endpoint.
//
// The makeCache factory is maintained once in frontend_shared/makeCache.js
// (@shared alias). Named exports here stay identical so all existing imports
// in pages/ are unchanged.
import { makeCache } from "@shared/makeCache";

const { cacheSet, cacheGet } = makeCache("masar_portal_cache:");

export { cacheSet, cacheGet };
