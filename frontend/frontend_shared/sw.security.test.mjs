import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

import { completeAssetTreeBuildId } from "./sw.build-id.js";
import { generate } from "./sw.generate.js";
import { SW_PARAMS } from "./sw.params.js";
import { renderServiceWorker } from "./sw.template.js";
import {
  LEGACY_APEX_WORKER_PATHS,
  reconcileServiceWorker,
} from "../worker/src/serviceWorkerRegistration.js";

const ROOT = path.resolve(import.meta.dirname, "../..");
const ASSET_TREE = path.join(ROOT, "apex/public/worker_portal");
const DRIVER_SW = path.join(ROOT, "apex/www/driver-sw.min.js");
const MASAR_SW = path.join(ROOT, "apex/www/masar-sw.min.js");
const TEST_BUILD = "deadbeef0000";
const ORIGIN = "https://apex.test";

function response(tag, { ok = true, redirected = false, type = "basic", contentType = "application/javascript" } = {}) {
  return {
    ok,
    redirected,
    type,
    headers: { get(name) { return name.toLowerCase() === "content-type" ? contentType : null; } },
    clone() { return this; },
    tag,
  };
}

function request(pathname, { method = "GET", mode, origin = ORIGIN } = {}) {
  return { url: origin + pathname, method, mode, clone() { return this; } };
}

class MemoryCache {
  constructor() { this.values = new Map(); }
  key(value) { return new URL(typeof value === "string" ? value : value.url, ORIGIN).href; }
  async match(value) { return this.values.get(this.key(value)); }
  async put(value, result) { this.values.set(this.key(value), result); }
}

function loadWorker(params) {
  const handlers = {};
  const buckets = new Map();
  const deleted = [];
  const opened = [];
  const fetches = [];
  const clientActions = [];
  let cacheNames = [];
  let fetchResult = (input) => {
    const url = new URL(typeof input === "string" ? input : input.url, ORIGIN);
    if (url.pathname.endsWith(".html")) return response("offline", { contentType: "text/html; charset=utf-8" });
    if (url.pathname.endsWith(".css")) return response("css", { contentType: "text/css" });
    if (url.pathname.endsWith(".woff2")) return response("font", { contentType: "font/woff2" });
    if (url.pathname.endsWith(".png")) return response("png", { contentType: "image/png" });
    return response("js");
  };
  const caches = {
    async open(name) {
      opened.push(name);
      if (!buckets.has(name)) buckets.set(name, new MemoryCache());
      return buckets.get(name);
    },
    async keys() { return cacheNames.length ? cacheNames : [...buckets.keys()]; },
    async delete(name) { deleted.push(name); buckets.delete(name); return true; },
  };
  const clients = {
    async matchAll() {
      return [{
        url: `${ORIGIN}${params.navPath}`,
        async navigate(url) { clientActions.push(["navigate", url]); },
        async focus() { clientActions.push(["focus"]); },
      }];
    },
    async openWindow(url) { clientActions.push(["open", url]); },
  };
  const self = {
    location: { origin: ORIGIN },
    registration: { async showNotification() {} },
    clients: { ...clients, async claim() {} },
    async skipWaiting() {},
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  const context = {
    AbortController,
    Request,
    URL,
    caches,
    clients,
    clearTimeout,
    console,
    fetch: async (input, options) => {
      fetches.push([input, options]);
      return fetchResult(input, options);
    },
    self,
    setTimeout,
  };
  vm.runInNewContext(renderServiceWorker({ ...params, build: TEST_BUILD }), context);

  async function dispatch(name, event = {}) {
    let responsePromise;
    const waits = [];
    event.respondWith = (value) => { responsePromise = Promise.resolve(value); };
    event.waitUntil = (value) => { waits.push(Promise.resolve(value)); };
    handlers[name]?.(event);
    await Promise.all(waits);
    return responsePromise;
  }

  return {
    buckets,
    clientActions,
    deleted,
    dispatch,
    fetches,
    opened,
    setCacheNames(names) { cacheNames = names; },
    setFetchResult(value) { fetchResult = value; },
  };
}

for (const [entry, navPath] of [["worker_portal", "/masar/"], ["driver_portal", "/driver/"]]) {
  test(`${entry} uses one canonical trailing-slash identity and a distinct cache namespace`, () => {
    const params = SW_PARAMS[entry];
    assert.equal(params.navPath, navPath);
    assert.equal(params.scope, navPath);
    assert.equal(params.appId, navPath);
    assert.match(params.cacheNamespace, new RegExp(`^apex:${entry === "worker_portal" ? "masar" : "driver"}:`));
  });

  test(`${entry} install caches only generic offline content and exact immutable assets`, async () => {
    const params = SW_PARAMS[entry];
    const worker = loadWorker(params);
    await worker.dispatch("install", {});
    const storedUrls = [...worker.buckets.values()].flatMap((cache) => [...cache.values.keys()]);
    assert(storedUrls.includes(new URL(params.offlinePath, ORIGIN).href));
    assert(!storedUrls.includes(new URL(params.navPath, ORIGIN).href), "personalized navigation HTML was cached");
    assert.deepEqual(
      storedUrls.sort(),
      [params.offlinePath, ...params.immutableAssets].map((value) => new URL(value, ORIGIN).href).sort(),
    );
  });

  test(`${entry} navigation is network-only and falls back only to generic offline HTML`, async () => {
    const params = SW_PARAMS[entry];
    const worker = loadWorker(params);
    await worker.dispatch("install", {});

    worker.setFetchResult(async () => response("personalized", { contentType: "text/html" }));
    const online = await worker.dispatch("fetch", { request: request(`${params.navPath}?token=secret`, { mode: "navigate" }) });
    assert.equal((await online).tag, "personalized");

    worker.setFetchResult(async () => { throw new Error("offline"); });
    const offline = await worker.dispatch("fetch", { request: request(params.navPath, { mode: "navigate" }) });
    assert.equal((await offline).tag, "offline");

    const storedUrls = [...worker.buckets.values()].flatMap((cache) => [...cache.values.keys()]);
    assert(!storedUrls.includes(new URL(params.navPath, ORIGIN).href));
  });

  test(`${entry} never handles API, files, cross-origin, or non-allowlisted requests`, async () => {
    const params = SW_PARAMS[entry];
    const worker = loadWorker(params);
    for (const req of [
      request("/api/method/apex.secret", { method: "POST" }),
      request("/files/private/photo.jpg"),
      request("/assets/apex/worker_portal/assets/not-allowlisted.js"),
      request(params.immutableAssets[0], { origin: "https://attacker.test" }),
    ]) {
      assert.equal(await worker.dispatch("fetch", { request: req }), undefined);
    }
    assert.equal(worker.opened.length, 0);
  });

  test(`${entry} caches allowlisted assets only after origin, status, redirect, and MIME validation`, async () => {
    const params = SW_PARAMS[entry];
    const asset = params.immutableAssets.find((value) => value.endsWith(".js"));
    assert(asset, "fixture needs one JavaScript asset");
    const cases = [
      response("redirect", { redirected: true }),
      response("login", { contentType: "text/html" }),
      response("wrong-mime", { contentType: "text/plain" }),
      response("not-ok", { ok: false }),
    ];
    for (const candidate of cases) {
      const worker = loadWorker(params);
      worker.setFetchResult(async () => candidate);
      assert.equal((await worker.dispatch("fetch", { request: request(asset) })).tag, candidate.tag);
      assert.equal([...worker.buckets.values()].flatMap((cache) => [...cache.values.keys()]).length, 0);
    }

    const worker = loadWorker(params);
    worker.setFetchResult(async () => response("valid-js"));
    assert.equal((await worker.dispatch("fetch", { request: request(asset) })).tag, "valid-js");
    assert.deepEqual(
      [...worker.buckets.values()].flatMap((cache) => [...cache.values.keys()]),
      [new URL(asset, ORIGIN).href],
    );
  });

  test(`${entry} deletes only caches in its exact entry namespace`, async () => {
    const params = SW_PARAMS[entry];
    const other = entry === "worker_portal" ? "driver" : "masar";
    const worker = loadWorker(params);
    const current = `${params.cacheNamespace}${TEST_BUILD}`;
    const stale = `${params.cacheNamespace}0123456789ab`;
    worker.setCacheNames([
      current,
      stale,
      `${entry === "worker_portal" ? "masar" : "driver"}-pwa-v9-0123456789ab-data`,
      `apex:${other}:0123456789ab`,
      `${params.cacheNamespace}0123456789ab:near-miss`,
      "another-app-cache",
    ]);
    await worker.dispatch("activate", {});
    assert.deepEqual(worker.deleted, [
      stale,
      `${entry === "worker_portal" ? "masar" : "driver"}-pwa-v9-0123456789ab-data`,
    ]);
  });
}

test("driver notification URLs stay on the canonical driver path", async () => {
  for (const [payload, expected] of [
    ["/driver/#/trip/1", `${ORIGIN}/driver/#/trip/1`],
    ["https://attacker.test/driver/", `${ORIGIN}/driver/`],
    ["//attacker.test/driver/", `${ORIGIN}/driver/`],
    ["/masar/", `${ORIGIN}/driver/`],
    ["/app/", `${ORIGIN}/driver/`],
  ]) {
    const worker = loadWorker(SW_PARAMS.driver_portal);
    await worker.dispatch("notificationclick", {
      notification: { close() {}, data: { url: payload } },
    });
    assert.deepEqual(worker.clientActions[0], ["navigate", expected]);
  }
});

test("both manifests use canonical standalone Arabic identities and approved colors", () => {
  for (const [filename, route] of [["manifest.webmanifest", "/masar/"], ["driver.webmanifest", "/driver/"]]) {
    const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "frontend/worker/public", filename)));
    assert.equal(manifest.id, route);
    assert.equal(manifest.start_url, route);
    assert.equal(manifest.scope, route);
    assert.equal(manifest.display, "standalone");
    assert.deepEqual(manifest.display_override, ["standalone"]);
    assert.equal(manifest.lang, "ar");
    assert.equal(manifest.dir, "rtl");
    assert.equal(manifest.theme_color, "#00844E");
    assert.equal(manifest.background_color, "#F8F5EE");
  }
});

test("each entry provides an opaque 180px Apple touch icon", () => {
  for (const entry of ["masar", "driver"]) {
    const png = fs.readFileSync(path.join(ROOT, `frontend/worker/public/icons/${entry}-apple-touch-icon-180.png`));
    assert.equal(png.readUInt32BE(16), 180);
    assert.equal(png.readUInt32BE(20), 180);
    assert.equal(png[25], 2, "Apple touch icon must be truecolor without an alpha channel");
  }
});

test("registration migration removes legacy Apex scripts and slashless scopes only", async () => {
  assert.deepEqual(LEGACY_APEX_WORKER_PATHS, ["/driver-sw.js", "/masar-sw.js"]);
  function registration(pathname, scope = `${ORIGIN}/driver/`) {
    return {
      active: { scriptURL: ORIGIN + pathname },
      scope,
      removed: false,
      async unregister() { this.removed = true; },
    };
  }
  const legacy = registration("/driver-sw.js");
  const slashlessCurrentScript = registration("/driver-sw.min.js", `${ORIGIN}/driver`);
  const current = registration("/driver-sw.min.js");
  const otherEntry = registration("/masar-sw.min.js", `${ORIGIN}/masar/`);
  const unrelated = registration("/service-worker.js");
  const registered = [];
  await reconcileServiceWorker({
    async getRegistrations() {
      return [legacy, slashlessCurrentScript, current, otherEntry, unrelated];
    },
    async register(script, options) { registered.push([script, options]); },
  }, { script: "/driver-sw.min.js", scope: "/driver/" });
  assert.equal(legacy.removed, true);
  assert.equal(slashlessCurrentScript.removed, true);
  assert.equal(current.removed, false);
  assert.equal(otherEntry.removed, false);
  assert.equal(unrelated.removed, false);
  assert.deepEqual(registered, [["/driver-sw.min.js", { scope: "/driver/" }]]);
});

test("registration requires a canonical trailing-slash scope", async () => {
  await assert.rejects(
    reconcileServiceWorker({ getRegistrations: async () => [], register: async () => {} }, {
      script: "/driver-sw.min.js",
      scope: "/driver",
    }),
    /canonical trailing-slash scope/,
  );
});

test("route adapters leave service-worker registration to the single runtime owner", () => {
  for (const adapter of ["apex/www/masar.html", "apex/www/driver.html"]) {
    const source = fs.readFileSync(path.join(ROOT, adapter), "utf8");
    assert.doesNotMatch(source, /navigator\.serviceWorker\s*\.register|serviceWorker\.register/);
  }
});

test("generated workers reconstruct byte-for-byte from the complete asset-tree build", () => {
  const build = completeAssetTreeBuildId(ASSET_TREE);
  assert.match(fs.readFileSync(DRIVER_SW, "utf8"), new RegExp(`const BUILD = "${build}"`));
  assert.match(fs.readFileSync(MASAR_SW, "utf8"), new RegExp(`const BUILD = "${build}"`));
  assert.equal(generate({ write: false }), true);
});
