// Copyright (c) 2026, afmcoltd

export function renderServiceWorker(p) {
  const offlineAssets = Array.isArray(p.offlineAssets) ? p.offlineAssets : [];
  const hasOfflineAssets = offlineAssets.length > 0;
  const cacheData = p.cacheData !== false;
  const networkOnlyApiPrefixes = p.networkOnlyApiPrefixes || [];

  const headerOfflineClause = hasOfflineAssets ? " licensed font assets are cache-first;" : "";
  const shellComment = hasOfflineAssets
    ? `// The app shell: the portal HTML document, the built SPA bundle, and the
// licensed Thmanyah stylesheet and fonts. The HTML is cached under ${p.navPath} (no query string) so
// an offline reload matches.`
    : `// The app shell: the portal HTML document and the built SPA bundle. No additional
// offline assets are precached. The HTML is cached under ${p.navPath} (no query
// string) so an offline reload matches.`;

  const offlineAssetShell = hasOfflineAssets
    ? "\n" + offlineAssets.map((asset) => `  ${JSON.stringify(asset)},`).join("\n")
    : "";

  const dataConds = (p.dataEndpoints || [])
    .map((ep) => `    url.pathname === ${JSON.stringify(ep)}`)
    .join(" ||\n");

  const apiClassifiers = [
    cacheData
      ? `// Portal data reads eligible for the Masar offline cache.
function isPortalDataRequest(url) {
  return (
${dataConds}
  );
}`
      : "",
    networkOnlyApiPrefixes.length
      ? `// Credential-scoped driver and boarding APIs are always network-only.
function isNetworkOnlyApiRequest(url) {
  return (
${networkOnlyApiPrefixes
  .map((prefix) => `    url.pathname.startsWith(${JSON.stringify(prefix)})`)
  .join(" ||\n")}
  );
}`
      : "",
  ].filter(Boolean).join("\n\n");

  const cacheFirstBlock = hasOfflineAssets
    ? `// Cache-first for the licensed, versioned font assets: serve instantly from
// cache, fetch+store on a miss. The versioned path changes when the font set changes.
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
    // The shared Apex app icon; client-neutral and guaranteed to exist.
    icon: "/assets/apex/images/apex-app-icon.svg",
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

  const offlineAssetFetchBranch = hasOfflineAssets
    ? `\n  // Exact licensed font assets: cache-first for resilient typography.
  if (OFFLINE_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }\n`
    : "";

  const prologue = `// Copyright (c) 2026, afmcoltd
// ${p.displayName} PWA service worker, served at ROOT (/${p.swFilename}) so its scope
// covers ${p.navPath}. Shell is NETWORK-FIRST;${headerOfflineClause} stale owned caches
// drop on activate. BUILD (full asset-tree hash, stamped per build) changes these bytes on
// each deploy -> updatefound.${p.skipWaitingOnInstall ? " Driver security builds activate immediately." : " Activates on SKIP_WAITING."}
// GENERATED — do not edit by hand. Single-sourced from frontend/frontend_shared/sw.template.js
// + sw.params.js. Regenerate: node frontend/frontend_shared/sw.generate.js --write
const BUILD = "${p.build}";

const CACHE_VERSION = "${p.cacheVersion}" + BUILD;
const CACHE_NAMESPACE = "${p.cacheNamespace}";
const SHELL_CACHE = CACHE_VERSION + "-shell";
const DATA_CACHE = ${cacheData ? 'CACHE_VERSION + "-data"' : "null"};

// How long to wait for the network before falling back to the cached shell on a
// slow (but not dead) connection.
const SHELL_NETWORK_TIMEOUT_MS = 3000;

const ASSET_BASE = "${p.assetBase}";
const OFFLINE_ASSETS = ${JSON.stringify(offlineAssets)};

${shellComment}
const SHELL_URLS = [
  "${p.navPath}",
  ASSET_BASE + "/assets/index.js",
  ASSET_BASE + "/assets/index.css",${offlineAssetShell}
];

${apiClassifiers}`;

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
      ${p.skipWaitingOnInstall
        ? "// Driver security updates take control without user interaction.\n      await self.skipWaiting();"
        : '// The Masar worker waits so its SPA can show the existing reload banner.'}
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
          .filter((k) => k.startsWith(CACHE_NAMESPACE))
          .filter((k) => k !== SHELL_CACHE && (!DATA_CACHE || k !== DATA_CACHE))
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

${networkOnlyApiPrefixes.length ? `
  if (isNetworkOnlyApiRequest(url)) {
    event.respondWith(fetch(request));
    return;
  }

` : ""}${cacheData ? `


  if (isPortalDataRequest(url) && (request.method === "GET" || request.method === "POST")) {
    event.respondWith(networkFirstData(request));
    return;
  }

` : ""}

  // Everything below is GET-only (navigations + static subresources).
  if (request.method !== "GET") return;

  // Navigation to ${p.navPath} (any query string): network-first so an online
  // worker boots the latest build; cached shell only when offline.
  if (request.mode === "navigate" && url.pathname === "${p.navPath}") {
    event.respondWith(networkFirstShell(request, "${p.navPath}"));
    return;
  }
${offlineAssetFetchBranch}
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
  ];
  if (cacheData) blocks.push(dataCacheKeyBlock, networkFirstDataBlock);
  blocks.push(fetchFreshBlock, networkFirstShellBlock);
  if (cacheFirstBlock) blocks.push(cacheFirstBlock);
  if (pushBlock) blocks.push(pushBlock);
  blocks.push(fetchListenerBlock);

  return blocks.join("\n\n") + "\n";
}
