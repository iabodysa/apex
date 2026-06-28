// [#t648-make-cache]
// Offline cache for read-only "today"/route payloads. The driver portal is used
// in the field where the network drops mid-shift; this lets a screen render the
// LAST successful response (labelled stale) instead of a bare error.
// Writes are never cached — only safe identity-scoped reads, keyed per endpoint.
//
// The makeCache factory is maintained once in frontend_shared/makeCache.js
// (@shared alias). Named exports here stay identical so all existing imports
// in App.vue and pages/ are unchanged.
import { makeCache } from "@shared/makeCache";

const { online, cacheSet, cacheGet } = makeCache("salis_portal_cache:");

export { online, cacheSet, cacheGet };
