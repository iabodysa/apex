function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function renderServiceWorker(params) {
  const pushHandlers = params.enablePush
    ? `
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = { body: event.data && event.data.text ? event.data.text() : "" };
  }
  event.waitUntil(self.registration.showNotification(data.title || ${JSON.stringify(params.push.title)}, {
    body: data.body || "",
    icon: ${JSON.stringify(params.push.icon)},
    data: { url: normalizeNotificationUrl(data.url) },
    tag: data.tag || ${JSON.stringify(params.push.tag)},
  }));
});

function normalizeNotificationUrl(candidate) {
  try {
    const target = new URL(candidate || NAV_PATH, self.location.origin);
    if (target.origin === self.location.origin && target.pathname.startsWith(NAV_PATH)) {
      return target.href;
    }
  } catch (error) {}
  return new URL(NAV_PATH, self.location.origin).href;
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = normalizeNotificationUrl(event.notification.data && event.notification.data.url);
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).pathname.startsWith(NAV_PATH) && "focus" in client) {
        if ("navigate" in client) await client.navigate(target);
        return client.focus();
      }
    }
    if (clients.openWindow) return clients.openWindow(target);
  })());
});`
    : "";

  return `// Generated from frontend/apex_portal/tooling/service-worker-template.js.
const BUILD = ${JSON.stringify(params.build)};
const NAV_PATH = ${JSON.stringify(params.navPath)};
const OFFLINE_PATH = ${JSON.stringify(params.offlinePath)};
const DURABLE_ASSETS = Object.freeze(${JSON.stringify(params.durableAssets)});
const VERSIONED_ASSETS = Object.freeze(${JSON.stringify(params.versionedAssets)});
const DURABLE_ASSET_SET = new Set(DURABLE_ASSETS);
const VERSIONED_ASSET_SET = new Set(VERSIONED_ASSETS);
const CACHE_NAMESPACE = ${JSON.stringify(params.cacheNamespace)};
// Two caches because the two lists retire on different events. A DURABLE_ASSETS URL carries its
// own version, so it is correct until it stops being listed and this cache is keyed by nothing.
// A VERSIONED_ASSETS URL is stable while its body is not, so only BUILD can retire it.
const DURABLE_CACHE = CACHE_NAMESPACE + "durable";
const CACHE_NAME = CACHE_NAMESPACE + BUILD;
const CACHE_NAME_PATTERN = new RegExp(${JSON.stringify(`^${escapeRegex(params.cacheNamespace)}[a-f0-9]{12}$`)});
const LEGACY_CACHE_PATTERNS = ${JSON.stringify(params.legacyCachePatterns || [])}.map((source) => new RegExp(source));

function expectedMime(pathname) {
  if (pathname.endsWith(".js")) return /(?:application|text)\\/javascript/i;
  if (pathname.endsWith(".css")) return /text\\/css/i;
  if (pathname.endsWith(".woff2")) return /font\\/woff2/i;
  if (pathname.endsWith(".png")) return /image\\/png/i;
  if (pathname.endsWith(".svg")) return /image\\/svg\\+xml/i;
  if (pathname.endsWith(".html")) return /text\\/html/i;
  return null;
}

function isSafeCacheResponse(pathname, response) {
  if (!response || !response.ok || response.redirected || response.type === "opaque") return false;
  const mime = expectedMime(pathname);
  const contentType = response.headers && response.headers.get("content-type");
  return Boolean(mime && contentType && mime.test(contentType));
}

async function fetchAndCache(cache, pathname) {
  const target = new URL(pathname, self.location.origin);
  if (target.origin !== self.location.origin) return;
  try {
    const response = await fetch(target.href, { cache: "reload", redirect: "error" });
    if (isSafeCacheResponse(target.pathname, response)) await cache.put(target.href, response.clone());
  } catch (error) {}
}

// Requests a durable asset only when its URL is not already held. Skipping a hit is what makes a
// deploy cheap: an unchanged chunk keeps its content-hashed URL, so the stored response is still
// the right bytes and no request is issued for it.
async function cacheOnce(cache, pathname) {
  const target = new URL(pathname, self.location.origin);
  if (await cache.match(target.href)) return;
  await fetchAndCache(cache, pathname);
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const durable = await caches.open(DURABLE_CACHE);
    const versioned = await caches.open(CACHE_NAME);
    await Promise.all([
      ...DURABLE_ASSETS.map((path) => cacheOnce(durable, path)),
      ...[OFFLINE_PATH, ...VERSIONED_ASSETS].map((path) => fetchAndCache(versioned, path)),
    ]);
${params.skipWaitingOnInstall ? "    await self.skipWaiting();" : ""}
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

// Drops the durable entries this build stopped listing, so a superseded chunk does not accumulate.
// Nothing else evicts them, because their cache name carries no build id.
async function pruneDurableCache() {
  const cache = await caches.open(DURABLE_CACHE);
  const stored = await cache.keys();
  await Promise.all(stored
    .filter((request) => !DURABLE_ASSET_SET.has(new URL(request.url).pathname))
    .map((request) => cache.delete(request)));
}

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name !== CACHE_NAME && name !== DURABLE_CACHE)
      .filter((name) => CACHE_NAME_PATTERN.test(name) || LEGACY_CACHE_PATTERNS.some((pattern) => pattern.test(name)))
      .map((name) => caches.delete(name)));
    await pruneDurableCache();
    await self.clients.claim();
  })());
});

async function navigationResponse(request) {
  try {
    return await fetch(request, { cache: "no-store", redirect: "manual" });
  } catch (error) {
    const cache = await caches.open(CACHE_NAME);
    const fallback = await cache.match(new URL(OFFLINE_PATH, self.location.origin).href);
    if (fallback) return fallback;
    throw error;
  }
}

async function immutableResponse(request, pathname) {
  const cache = await caches.open(DURABLE_ASSET_SET.has(pathname) ? DURABLE_CACHE : CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request, { cache: "reload", redirect: "error" });
  if (isSafeCacheResponse(pathname, response)) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  let url;
  try {
    url = new URL(request.url);
  } catch (error) {
    return;
  }
  if (url.origin !== self.location.origin || request.method !== "GET") return;
  if (request.mode === "navigate" && url.pathname === NAV_PATH) {
    event.respondWith(navigationResponse(request));
    return;
  }
  if (DURABLE_ASSET_SET.has(url.pathname) || VERSIONED_ASSET_SET.has(url.pathname)) {
    event.respondWith(immutableResponse(request, url.pathname));
  }
});
${pushHandlers}`.trimEnd() + "\n";
}
