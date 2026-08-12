import { describe, expect, it } from "vitest";
import { renderServiceWorker } from "@shared/sw.template.js";
import { SW_PARAMS } from "@shared/sw.params.js";

const ORIGIN = "https://bench.local";
const BUILD = "deadbeef0000";

function result(tag, { ok = true, redirected = false, contentType = "application/javascript" } = {}) {
  return {
    ok,
    redirected,
    type: "basic",
    headers: { get: (name) => name === "content-type" ? contentType : null },
    _tag: tag,
    clone() { return this; },
  };
}

function goodAsset(input) {
  const url = new URL(typeof input === "string" ? input : input.url, ORIGIN);
  const contentType = url.pathname.endsWith(".html") ? "text/html"
    : url.pathname.endsWith(".css") ? "text/css"
      : url.pathname.endsWith(".woff2") ? "font/woff2"
        : url.pathname.endsWith(".png") ? "image/png"
          : "application/javascript";
  return result(url.pathname, { contentType });
}

function makeRequest(pathname, { method = "GET", mode } = {}) {
  return { url: ORIGIN + pathname, method, mode, clone() { return this; } };
}

class Cache {
  constructor() { this.values = new Map(); }
  key(value) { return new URL(typeof value === "string" ? value : value.url, ORIGIN).href; }
  async match(value) { return this.values.get(this.key(value)); }
  async put(value, response) { this.values.set(this.key(value), response); }
}

function loadWorker(params) {
  const listeners = {};
  const stores = new Map();
  const state = { fetch: async (input) => goodAsset(input), skipWaiting: 0 };
  const deleted = [];
  let namedCaches = null;

  const caches = {
    async open(name) {
      if (!stores.has(name)) stores.set(name, new Cache());
      return stores.get(name);
    },
    async keys() { return namedCaches || [...stores.keys()]; },
    async delete(name) { deleted.push(name); stores.delete(name); return true; },
  };
  const clients = { matchAll: async () => [], openWindow: async () => null };
  const self = {
    location: { origin: ORIGIN },
    clients: { ...clients, claim: async () => {} },
    registration: { showNotification: async () => {} },
    addEventListener: (name, listener) => { listeners[name] = listener; },
    skipWaiting: async () => { state.skipWaiting += 1; },
  };
  const sandbox = {
    AbortController,
    Request,
    URL,
    caches,
    clients,
    clearTimeout,
    console,
    fetch: (input, options) => state.fetch(input, options),
    self,
    setTimeout,
  };
  const code = renderServiceWorker({ ...params, build: BUILD });
  // eslint-disable-next-line no-new-func
  new Function(...Object.keys(sandbox), `"use strict";\n${code}`)(...Object.values(sandbox));

  async function dispatch(name, event = {}) {
    const waits = [];
    let response;
    event.waitUntil = (value) => waits.push(Promise.resolve(value));
    event.respondWith = (value) => { response = Promise.resolve(value); };
    listeners[name]?.(event);
    await Promise.all(waits);
    return response;
  }

  return {
    code,
    deleted,
    dispatch,
    setCacheNames(names) { namedCaches = names; },
    state,
    stores,
  };
}

for (const [name, params] of Object.entries(SW_PARAMS)) {
  describe(`${name} service worker`, () => {
    it("precaches only generic offline content and exact immutable assets", async () => {
      const worker = loadWorker(params);
      await worker.dispatch("install");
      const values = [...worker.stores.values()].flatMap((cache) => [...cache.values.keys()]);
      expect(values.sort()).toEqual(
        [params.offlinePath, ...params.immutableAssets]
          .map((value) => new URL(value, ORIGIN).href)
          .sort(),
      );
      expect(values).not.toContain(new URL(params.navPath, ORIGIN).href);
    });

    it("leaves credential APIs and files entirely network-only", async () => {
      const worker = loadWorker(params);
      expect(await worker.dispatch("fetch", {
        request: makeRequest("/api/method/apex.private", { method: "POST" }),
      })).toBeUndefined();
      expect(await worker.dispatch("fetch", {
        request: makeRequest("/files/private/evidence.jpg"),
      })).toBeUndefined();
      expect(worker.stores.size).toBe(0);
    });

    it("never caches navigation HTML and uses only generic offline fallback", async () => {
      const worker = loadWorker(params);
      await worker.dispatch("install");
      worker.state.fetch = async () => result("personalized", { contentType: "text/html" });
      expect((await worker.dispatch("fetch", {
        request: makeRequest(`${params.navPath}?token=secret`, { mode: "navigate" }),
      }))._tag).toBe("personalized");
      worker.state.fetch = async () => { throw new Error("offline"); };
      expect((await worker.dispatch("fetch", {
        request: makeRequest(params.navPath, { mode: "navigate" }),
      }))._tag).toBe(params.offlinePath);
      const values = [...worker.stores.values()].flatMap((cache) => [...cache.values.keys()]);
      expect(values).not.toContain(new URL(params.navPath, ORIGIN).href);
    });

    it("deletes only stale names from its exact entry namespace", async () => {
      const worker = loadWorker(params);
      const current = params.cacheNamespace + BUILD;
      const stale = params.cacheNamespace + "0123456789ab";
      const other = name === "worker_portal" ? "apex:driver:0123456789ab" : "apex:masar:0123456789ab";
      const legacy = `${name === "worker_portal" ? "masar" : "driver"}-pwa-v9-0123456789ab-data`;
      worker.setCacheNames([current, stale, legacy, `${stale}:near-miss`, other, "unrelated"]);
      await worker.dispatch("activate");
      expect(worker.deleted).toEqual([stale, legacy]);
    });

    it("serves only exact allowlisted assets from cache", async () => {
      const worker = loadWorker(params);
      await worker.dispatch("install");
      worker.state.fetch = async () => { throw new Error("offline"); };
      const asset = params.immutableAssets.at(-1);
      expect((await worker.dispatch("fetch", { request: makeRequest(asset) }))._tag).toBe(asset);
      expect(await worker.dispatch("fetch", {
        request: makeRequest("/assets/apex/worker_portal/assets/not-allowlisted.js"),
      })).toBeUndefined();
    });
  });
}

describe("Masar service-worker updates", () => {
  it("keeps the worker entry user-controlled and activates driver security updates", async () => {
    const masar = loadWorker(SW_PARAMS.worker_portal);
    await masar.dispatch("install");
    expect(masar.state.skipWaiting).toBe(0);
    await masar.dispatch("message", { data: { type: "SKIP_WAITING" } });
    expect(masar.state.skipWaiting).toBe(1);

    const driver = loadWorker(SW_PARAMS.driver_portal);
    await driver.dispatch("install");
    expect(driver.state.skipWaiting).toBe(1);
  });
});
