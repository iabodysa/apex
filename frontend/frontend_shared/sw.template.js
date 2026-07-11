// Copyright (c) 2026, AFMCO and contributors
//
// Single source for BOTH portal service workers (driver + masar). renderServiceWorker(p)
// returns the full text of one www/*-sw.min.js from a per-portal params object (see
// sw.params.js). The two SWs share 100% of their caching LOGIC; only real behavioural
// differences are parameterized:
//   - fonts        : masar self-hosts fonts (precache + cache-first branch); driver does
//                    not (CDN fonts, left to the browser HTTP cache). p.fonts drives both
//                    the SHELL_URLS precache list AND the presence of the cache-first
//                    fetch branch. Empty => neither is emitted.
//   - enablePush   : driver ships Web Push (push + notificationclick handlers); masar does
//                    not. Toggles those two handlers so masar never gains push behaviour.
//   - cacheVersion : "driver-pwa-v1-" vs "masar-pwa-v3-" — the version segment is portal
//                    state (bumped independently to force a cache reset); NOT unified.
//   - assetBase / navPath / dataEndpoints / dataCacheHost / displayName / swFilename.
//   - build        : the bundle content-hash, injected by the stampServiceWorker vite
//                    plugin (or, for a standalone regen, carried forward from the file).
//
// The emitted file is byte-reconstructable: renderServiceWorker(params) with the same
// `build` reproduces the committed bytes exactly (see sw.generate.js --check).

export function renderServiceWorker(p) {
  const hasFonts = Array.isArray(p.fonts) && p.fonts.length > 0;

  const headerFontClause = hasFonts ? " fonts are cache-first;" : "";
  const shellComment = hasFonts
    ? `// The app shell: the portal HTML document, the built SPA bundle, and the
// self-hosted fonts. The HTML is cached under ${p.navPath} (no query string) so
// an offline reload matches.`
    : `// The app shell: the portal HTML document and the built SPA bundle. Fonts load
// from a CDN (not self-hosted), left to the browser HTTP cache. The HTML is cached
// under ${p.navPath} (no query string) so an offline reload matches.`;

  const fontShell = hasFonts
    ? "\n" + p.fonts.map((f) => `  ASSET_BASE + "/fonts/${f}.woff2",`).join("\n")
    : "";

  const dataConds = p.dataEndpoints
    .map((ep) => `    url.pathname === ${JSON.stringify(ep)}`)
    .join(" ||\n");

  const cacheFirstBlock = hasFonts
    ? `// Cache-first for immutable assets (self-hosted fonts): serve instantly from
// cache, fetch+store on a miss. Fonts never change, so no revalidation needed.
async function cacheFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const res = await fetch(request);
  if (res && res.ok) cache.put(request, res.clone());
  return res;
}`
    : "";

  const pushBlock = p.enablePush
    ? `// Web Push: show a notification when the push service delivers one. The payload is
// the small JSON the server sends ({title, body, url}); a bodyless push (e.g. a
// keepalive) falls back to a generic title so the OS still surfaces it. Background
// push only fires when the driver opted in AND the owner configured VAPID, so this
// handler is inert until push is wired — no-op-safe.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data && event.data.text ? event.data.text() : "" };
  }
  const title = data.title || ${JSON.stringify(p.push.title)};
  const options = {
    body: data.body || "",
    // The PWA's own logo (same asset the manifest uses); guaranteed to exist.
    icon: ASSET_BASE + "/afmco-logo.svg",
    data: { url: data.url || ${JSON.stringify(p.navPath)} },
    tag: data.tag || ${JSON.stringify(p.push.tag)},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Tapping a push focuses an open ${p.navPath} tab (navigating it to the deep-link path)
// or opens one, so the user lands on the relevant screen.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || ${JSON.stringify(p.navPath)};
  event.waitUntil(
    (async () => {
      const all = await clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of all) {
        if (client.url.includes(${JSON.stringify(p.navPath)}) && "focus" in client) {
          if ("navigate" in client) {
            try {
              await client.navigate(target);
            } catch (e) {}
          }
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })(),
  );
});`
    : "";

  const fontsFetchBranch = hasFonts
    ? `\n  // Self-hosted fonts: immutable -> cache-first for speed.
  if (url.pathname.startsWith(ASSET_BASE + "/fonts/")) {
    event.respondWith(cacheFirst(request));
    return;
  }\n`
    : "";

  const prologue = `// Copyright (c) 2026, AFMCO and contributors
// ${p.displayName} PWA service worker. Served at ROOT (/${p.swFilename}) so its scope
// covers ${p.navPath}; *.min.js under www/ ships as static source (no Jinja). Shell +
// portal data API are NETWORK-FIRST (latest build/data win online, cache only when
// unreachable, bounded timeout);${headerFontClause} stale caches drop on activate. BUILD
// is the bundle content-hash stamped by the vite plugin each build, so a deploy changes
// these bytes -> updatefound -> reload banner. The worker does NOT auto-skipWaiting; it
// activates only when the banner posts SKIP_WAITING.
//
// GENERATED FILE — do not edit by hand. Single-sourced from frontend/frontend_shared/
// sw.template.js + sw.params.js. Regenerate:
//   node frontend/frontend_shared/sw.generate.js --write
const BUILD = "${p.build}";

const CACHE_VERSION = "${p.cacheVersion}" + BUILD;
const SHELL_CACHE = CACHE_VERSION + "-shell";
const DATA_CACHE = CACHE_VERSION + "-data";

// How long to wait for the network before falling back to the cached shell on a
// slow (but not dead) connection.
const SHELL_NETWORK_TIMEOUT_MS = 3000;

const ASSET_BASE = "${p.assetBase}";

${shellComment}
const SHELL_URLS = [
  "${p.navPath}",
  ASSET_BASE + "/assets/index.js",
  ASSET_BASE + "/assets/index.css",${fontShell}
];

// Identifies a portal data read that is safe to runtime-cache for offline use
// (identity-scoped reads the portal paints from; writes are never cached).
function isPortalDataRequest(url) {
  return (
${dataConds}
  );
}`;

  const installBlock = `self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Cache each shell URL independently: one missing/redirected asset must
      // not abort the whole precache (addAll is all-or-nothing). cache:"reload"
      // bypasses the browser HTTP cache so the precache stores the fresh build.
      await Promise.all(
        SHELL_URLS.map(async (url) => {
          try {
            const res = await fetch(url, { cache: "reload" });
            if (res && (res.ok || res.type === "opaque")) {
              await cache.put(url, res.clone());
            }
          } catch (e) {
            // Best-effort precache; runtime fetch handler will retry online.
          }
        }),
      );
      // Intentionally NOT skipWaiting() here: the new worker waits in "installed"
      // so the SPA can show a reload banner; it activates only on SKIP_WAITING.
    })(),
  );
});`;

  const messageBlock = `// The reload banner posts SKIP_WAITING to activate the waiting worker on demand,
// so the worker decides when the new build takes over (vs an abrupt auto-reload).
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});`;

  const activateBlock = `self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== DATA_CACHE)
          .map((k) => caches.delete(k)),
      );
      await self.clients.claim();
    })(),
  );
});`;

  const dataCacheKeyBlock = `// The portal data API is issued by frappe-ui as a POST (args travel in the JSON
// body), and the Cache API cannot store a POST. So we cache under a SYNTHESIZED
// GET key built from the endpoint path + the request body, which is stable per
// read. This lets a POST read be served from cache offline while staying
// network-first online.
async function dataCacheKey(url, bodyText) {
  return new Request(
    "https://${p.dataCacheHost}" + url.pathname + "#" + encodeURIComponent(bodyText || ""),
    { method: "GET" },
  );
}`;

  const networkFirstDataBlock = `// Network-first for the portal data API (GET or POST): always try the network
// first so online data is fresh; only fall back to the last cached response when
// the network is unreachable.
async function networkFirstData(request) {
  const cache = await caches.open(DATA_CACHE);
  const url = new URL(request.url);
  // Read the body once (POST); GET has none. Clone so the network fetch still
  // has a consumable body.
  let bodyText = "";
  if (request.method === "POST") {
    try {
      bodyText = await request.clone().text();
    } catch (e) {}
  }
  const key = await dataCacheKey(url, bodyText);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      // Store a GET-keyed copy of the JSON response for offline use.
      cache.put(key, fresh.clone());
    }
    return fresh;
  } catch (e) {
    const cached = await cache.match(key);
    if (cached) return cached;
    throw e;
  }
}`;

  const fetchFreshBlock = `// Fetch the freshest copy, bypassing the browser HTTP cache, bounded by a
// timeout so a slow link falls back to cache instead of hanging. cache:"reload"
// guarantees a rebuilt same-filename asset (index.js) is actually refetched.
function fetchFresh(request) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), SHELL_NETWORK_TIMEOUT_MS);
  return fetch(request, { cache: "reload", signal: controller.signal }).finally(() =>
    clearTimeout(timer),
  );
}`;

  const networkFirstShellBlock = `// Network-first for the app shell (navigation + built bundle): an online worker
// always boots the latest build; the cached shell is the fallback when the
// network is unreachable or too slow (offline-capable). Keeps the cache warm by
// storing every successful response under a stable key.
async function networkFirstShell(request, shellKey) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const res = await fetchFresh(request);
    if (res && res.ok) cache.put(shellKey || request, res.clone());
    return res;
  } catch (e) {
    const cached = await cache.match(shellKey || request);
    if (cached) return cached;
    throw e;
  }
}`;

  const fetchListenerBlock = `self.addEventListener("fetch", (event) => {
  const request = event.request;

  let url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return;
  }

  // Only handle our own origin.
  if (url.origin !== self.location.origin) return;

  // Portal data API: network-first, fall back to cache offline. frappe-ui issues
  // these as POST (args in the body), so we handle GET and POST and key the cache
  // on the body — see networkFirstData.
  if (isPortalDataRequest(url) && (request.method === "GET" || request.method === "POST")) {
    event.respondWith(networkFirstData(request));
    return;
  }

  // Everything below is GET-only (navigations + static subresources).
  if (request.method !== "GET") return;

  // Navigation to ${p.navPath} (any query string): network-first so an online
  // worker boots the latest build; cached shell only when offline.
  if (request.mode === "navigate" && url.pathname === "${p.navPath}") {
    event.respondWith(networkFirstShell(request, "${p.navPath}"));
    return;
  }
${fontsFetchBranch}
  // Built bundle (index.js/index.css): network-first so a rebuild is picked up
  // immediately online; cached copy only when offline.
  if (url.pathname.startsWith(ASSET_BASE + "/assets/")) {
    event.respondWith(networkFirstShell(request));
    return;
  }
});`;

  const blocks = [
    prologue,
    installBlock,
    messageBlock,
    activateBlock,
    dataCacheKeyBlock,
    networkFirstDataBlock,
    fetchFreshBlock,
    networkFirstShellBlock,
  ];
  if (cacheFirstBlock) blocks.push(cacheFirstBlock);
  if (pushBlock) blocks.push(pushBlock);
  blocks.push(fetchListenerBlock);

  return blocks.join("\n\n") + "\n";
}
