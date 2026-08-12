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
    icon: "/assets/apex/images/apex-app-icon.svg",
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
const IMMUTABLE_ASSETS = Object.freeze(${JSON.stringify(params.immutableAssets)});
const IMMUTABLE_ASSET_SET = new Set(IMMUTABLE_ASSETS);
const CACHE_NAMESPACE = ${JSON.stringify(params.cacheNamespace)};
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

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all([OFFLINE_PATH, ...IMMUTABLE_ASSETS].map((path) => fetchAndCache(cache, path)));
${params.skipWaitingOnInstall ? "    await self.skipWaiting();" : ""}
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name !== CACHE_NAME)
      .filter((name) => CACHE_NAME_PATTERN.test(name) || LEGACY_CACHE_PATTERNS.some((pattern) => pattern.test(name)))
      .map((name) => caches.delete(name)));
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
  const cache = await caches.open(CACHE_NAME);
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
  if (IMMUTABLE_ASSET_SET.has(url.pathname)) {
    event.respondWith(immutableResponse(request, url.pathname));
  }
});
${pushHandlers}`.trimEnd() + "\n";
}
