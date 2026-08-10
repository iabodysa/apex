// Copyright (c) 2026, AFMCO and contributors
//
// Behavioural contract for the two single-sourced portal service workers. We render
// each SW from sw.template.js + sw.params.js, run it inside a mocked ServiceWorker
// global scope (Cache Storage keyed by ABSOLUTE URL, like a real browser), and drive
// the lifecycle + fetch events. Six cases lock the caching behaviour that the earlier
// hand-maintained files had — most importantly that Masar can cache its worker data
// while driver and boarding APIs remain network-only across driver credentials.
import { describe, it, expect, beforeEach } from "vitest";
import { renderServiceWorker } from "@shared/sw.template.js";
import { SW_PARAMS } from "@shared/sw.params.js";

const ORIGIN = "https://bench.local";
const TEST_BUILD = "deadbeef0000";
const THMANYAH_BASE = "/assets/apex/vendor/thmanyah-v1";
const THMANYAH_ASSETS = [
  `${THMANYAH_BASE}/thmanyah.css`,
  ...["Light", "Regular", "Medium", "Bold", "Black"].flatMap((weight) => [
    `${THMANYAH_BASE}/thmanyahsans-${weight}.woff2`,
    `${THMANYAH_BASE}/thmanyahserifdisplay-${weight}.woff2`,
    `${THMANYAH_BASE}/thmanyahseriftext-${weight}.woff2`,
  ]),
];

// A minimal Response stand-in: cacheable (clone) and taggable so a test can prove
// WHICH response a fetch resolved to (fresh network vs served-from-cache).
function makeRes(tag, { ok = true, type = "basic" } = {}) {
  return { ok, type, _tag: tag, clone() { return this; } };
}

// A fetch Request stand-in for a runtime fetch event.
function makeReq({ url, method = "GET", mode = undefined, body = undefined }) {
  return { url, method, mode, clone() { return this; }, async text() { return body || ""; } };
}

// Cache Storage that keys by absolute URL (relative precache strings resolve against
// ORIGIN exactly as the browser Cache API does), so a precached "/x" matches a runtime
// request for "https://origin/x".
class MockCache {
  constructor(base) { this.base = base; this.store = new Map(); }
  _k(x) { return new URL(typeof x === "string" ? x : x.url, this.base).href; }
  async put(req, res) { this.store.set(this._k(req), res); }
  async match(req) { return this.store.get(this._k(req)); }
}

// Build a fresh mocked SW global scope and execute the rendered worker inside it.
function loadSW(params) {
  const listeners = {};
  const cacheStorage = new Map();
  const state = { skipWaiting: 0, fetchImpl: async () => makeRes("network") };

  const caches = {
    async open(name) {
      if (!cacheStorage.has(name)) cacheStorage.set(name, new MockCache(ORIGIN));
      return cacheStorage.get(name);
    },
    async keys() { return [...cacheStorage.keys()]; },
    async delete(name) { return cacheStorage.delete(name); },
    async match(req) {
      for (const c of cacheStorage.values()) {
        const r = await c.match(req);
        if (r) return r;
      }
      return undefined;
    },
  };

  const clients = { matchAll: async () => [], openWindow: async () => null };
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type, fn) => (listeners[type] ||= []).push(fn),
    skipWaiting: () => { state.skipWaiting++; },
    clients: { claim: async () => {}, matchAll: clients.matchAll },
    registration: { showNotification: async () => {} },
  };
  const fetch = (input, opts) => state.fetchImpl(input, opts);

  const code = renderServiceWorker({ ...params, build: TEST_BUILD });
  const sandbox = {
    self, caches, clients, fetch, URL, Request: class {
      constructor(url, opts = {}) { this.url = typeof url === "string" ? url : url.url; this.method = (opts && opts.method) || "GET"; }
    },
    setTimeout, clearTimeout, AbortController, Promise, encodeURIComponent, console,
  };
  // eslint-disable-next-line no-new-func
  new Function(...Object.keys(sandbox), `"use strict";\n${code}`)(...Object.values(sandbox));

  async function dispatch(type, event = {}) {
    const waits = [];
    let responded = false;
    let response;
    event.waitUntil = (p) => waits.push(Promise.resolve(p).catch(() => {}));
    event.respondWith = (p) => { responded = true; response = Promise.resolve(p); };
    for (const fn of listeners[type] || []) await fn(event);
    await Promise.allSettled(waits);
    return { responded, response: responded ? await response : undefined };
  }

  const shellCache = () => [...cacheStorage.entries()].find(([n]) => n.endsWith("-shell"))?.[1];

  return { params, code, cacheStorage, caches, state, dispatch, shellCache };
}

const DRIVER = SW_PARAMS.driver_portal;
const MASAR = SW_PARAMS.worker_portal;

describe("portal service worker — install", () => {
  it("uses the Masar product name for both role-specific entry workers", () => {
    expect(DRIVER.displayName).toBe("Masar");
    expect(DRIVER.push.title).toBe("Masar");
    expect(MASAR.displayName).toBe("Masar");
  });

  it("precaches every shell URL and declared offline asset on install", async () => {
    for (const params of [DRIVER, MASAR]) {
      const sw = loadSW(params);
      sw.state.fetchImpl = async () => makeRes("shell");
      await sw.dispatch("install");
      const cache = sw.shellCache();
      expect(cache, `${params.swFilename}: shell cache created`).toBeTruthy();
      // nav path + index.js + index.css + each exact offline asset URL.
      expect(cache.store.size).toBe(3 + params.offlineAssets.length);
      expect(await cache.match(params.navPath), "nav shell precached").toBeTruthy();
      expect(sw.state.skipWaiting).toBe(params.skipWaitingOnInstall ? 1 : 0);
    }
    expect(DRIVER.offlineAssets).toEqual(THMANYAH_ASSETS);
    expect(MASAR.offlineAssets).toEqual(THMANYAH_ASSETS);
    expect(DRIVER.offlineAssets).toBe(MASAR.offlineAssets);
  });
});

describe("portal service worker — activate cleanup", () => {
  it("deletes every driver data cache without touching Masar caches", async () => {
    const sw = loadSW(DRIVER);
    sw.state.fetchImpl = async () => makeRes("shell");
    await sw.dispatch("install"); // creates the current -shell cache
    await sw.caches.open("driver-pwa-v0-oldhash-shell"); // a stale generation
    await sw.caches.open(`driver-pwa-v1-${TEST_BUILD}-data`);
    await sw.caches.open("driver-pwa-v0-oldhash-data");
    await sw.caches.open("masar-pwa-v3-current-data");

    await sw.dispatch("activate");

    expect(sw.cacheStorage.has("driver-pwa-v0-oldhash-shell"), "stale cache purged").toBe(false);
    expect(sw.cacheStorage.has(`driver-pwa-v1-${TEST_BUILD}-data`)).toBe(false);
    expect(sw.cacheStorage.has("driver-pwa-v0-oldhash-data")).toBe(false);
    expect(sw.cacheStorage.has("masar-pwa-v3-current-data")).toBe(true);
    expect(sw.shellCache(), "current shell cache retained").toBeTruthy();
  });
});

describe("masar service worker — credential APIs", () => {
  // Masar used to cache these reads under one key for every worker, so a reissued token
  // or a shared phone showed the previous worker's housing, documents and custody. The
  // offline fallback that behaviour bought is not worth a credential bleed.
  it("never caches or offline-serves worker API data", async () => {
    const sw = loadSW(MASAR);
    const ep = MASAR.networkOnlyApiPrefixes[0] + "get_worker_accommodation";
    const request = () => makeReq({ url: ORIGIN + ep, method: "POST", body: "{}" });

    sw.state.fetchImpl = async () => makeRes("worker-a");
    const online = await sw.dispatch("fetch", { request: request() });
    expect(online.response._tag).toBe("worker-a");
    expect([...sw.cacheStorage.keys()].some((name) => name.endsWith("-data"))).toBe(false);

    sw.state.fetchImpl = async () => { throw new Error("offline"); };
    await expect(sw.dispatch("fetch", { request: request() })).rejects.toThrow("offline");
    expect([...sw.cacheStorage.keys()].some((name) => name.endsWith("-data"))).toBe(false);
  });
});

describe("driver service worker — credential APIs", () => {
  it("never caches or offline-serves driver API data", async () => {
    const sw = loadSW(DRIVER);
    const ep = DRIVER.networkOnlyApiPrefixes[0] + "get_driver_profile";
    const request = () => makeReq({ url: ORIGIN + ep, method: "POST", body: "{}" });

    sw.state.fetchImpl = async () => makeRes("driver-a");
    const online = await sw.dispatch("fetch", { request: request() });
    expect(online.response._tag).toBe("driver-a");
    expect([...sw.cacheStorage.keys()].some((name) => name.endsWith("-data"))).toBe(false);

    sw.state.fetchImpl = async () => { throw new Error("offline"); };
    await expect(sw.dispatch("fetch", { request: request() })).rejects.toThrow("offline");
    expect([...sw.cacheStorage.keys()].some((name) => name.endsWith("-data"))).toBe(false);
  });
});

describe("portal service worker — shell network fallback", () => {
  it("returns the cached app shell for a navigation when the network is unreachable", async () => {
    const sw = loadSW(MASAR);
    sw.state.fetchImpl = async () => makeRes("shell");
    await sw.dispatch("install"); // warms the shell cache with navPath

    sw.state.fetchImpl = async () => { throw new Error("offline"); };
    const r = await sw.dispatch("fetch", {
      request: makeReq({ url: ORIGIN + MASAR.navPath + "?w=token", mode: "navigate" }),
    });
    expect(r.responded).toBe(true);
    expect(r.response._tag, "offline navigation falls back to cached shell").toBe("shell");
  });
});

describe("portal service worker — licensed font caching", () => {
  it("both entry workers serve the exact Thmanyah stylesheet and fonts cache-first", async () => {
    for (const params of [DRIVER, MASAR]) {
      const sw = loadSW(params);
      sw.state.fetchImpl = async () => makeRes("licensed-font");
      await sw.dispatch("install");
      sw.state.fetchImpl = async () => { throw new Error("offline"); };
      for (const asset of [THMANYAH_ASSETS[0], THMANYAH_ASSETS.at(-1)]) {
        const result = await sw.dispatch("fetch", { request: makeReq({ url: ORIGIN + asset }) });
        expect(result.responded, `${params.navPath} handles ${asset}`).toBe(true);
        expect(result.response._tag, `${params.navPath} serves ${asset} cache-first`).toBe("licensed-font");
      }
      expect(sw.code).toContain("cacheFirst");
      expect(sw.code).toContain(THMANYAH_BASE);
    }
  });
});

describe("Masar service worker — update via SKIP_WAITING", () => {
  it("keeps Masar's waiting worker user-controlled", async () => {
    const sw = loadSW(MASAR);
    await sw.dispatch("message", { data: { type: "SOMETHING_ELSE" } });
    expect(sw.state.skipWaiting, "unrelated message does not skipWaiting").toBe(0);
    await sw.dispatch("message", { data: { type: "SKIP_WAITING" } });
    expect(sw.state.skipWaiting, "SKIP_WAITING triggers skipWaiting()").toBe(1);
  });
});
