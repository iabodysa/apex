// Copyright (c) 2026, AFMCO and contributors
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

import { completeAssetTreeBuildId } from "./sw.build-id.js";

const ROOT = path.resolve(import.meta.dirname, "../..");
const ASSET_TREE = path.join(ROOT, "apex/public/worker_portal");
const DRIVER_SW = path.join(ROOT, "apex/www/driver-sw.min.js");
const MASAR_SW = path.join(ROOT, "apex/www/masar-sw.min.js");

function filesBelow(root, current = root) {
  return fs.readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(current, entry.name);
    return entry.isDirectory() ? filesBelow(root, absolute) : [absolute];
  });
}

function completeTreeBuildId(root) {
  const hash = crypto.createHash("sha256");
  for (const absolute of filesBelow(root).sort()) {
    const relative = path.relative(root, absolute).split(path.sep).join("/");
    hash.update(relative);
    hash.update("\0");
    hash.update(fs.readFileSync(absolute));
    hash.update("\0");
  }
  return hash.digest("hex").slice(0, 12);
}

function buildId(source) {
  return source.match(/const BUILD = "([^"]+)";/)?.[1];
}

function loadDriverWorker() {
  const handlers = {};
  const cacheBuckets = new Map();
  let cacheOpenCount = 0;
  const deletedCaches = [];
  let cacheNames = [];
  let fetchMode = "online";
  let skipWaitingCount = 0;
  let claimCount = 0;
  const responseA = { ok: true, driver: "A", clone() { return this; } };
  const keyOf = (key) => typeof key === "string" ? key : key.url;
  const caches = {
    async open(name) {
      cacheOpenCount += 1;
      if (!cacheBuckets.has(name)) cacheBuckets.set(name, new Map());
      const bucket = cacheBuckets.get(name);
      return {
        async match(key) { return bucket.get(keyOf(key)); },
        async put(key, value) { bucket.set(keyOf(key), value); },
      };
    },
    async keys() { return cacheNames; },
    async delete(name) { deletedCaches.push(name); return true; },
  };
  const self = {
    location: { origin: "https://driver.test" },
    clients: { async claim() { claimCount += 1; } },
    async skipWaiting() { skipWaitingCount += 1; },
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  const context = {
    AbortController,
    Request,
    URL,
    caches,
    clients: self.clients,
    clearTimeout,
    console,
    fetch: async () => {
      if (fetchMode === "offline") throw new Error("offline");
      return responseA;
    },
    self,
    setTimeout,
  };
  vm.runInNewContext(fs.readFileSync(DRIVER_SW, "utf8"), context);
  return {
    deletedCaches,
    handlers,
    responseA,
    cacheOpenCount: () => cacheOpenCount,
    claimCount: () => claimCount,
    skipWaitingCount: () => skipWaitingCount,
    setCacheNames: (names) => { cacheNames = names; },
    setFetchMode: (mode) => { fetchMode = mode; },
  };
}

function driverApiRequest() {
  return {
    url: "https://driver.test/api/method/apex.salis.api.driver_portal.get_driver_profile",
    method: "POST",
    clone() { return this; },
    async text() { return "{}"; },
  };
}

async function dispatchFetch(worker, request) {
  let response;
  worker.handlers.fetch({ request, respondWith(value) { response = value; } });
  return response;
}

test("both service workers use the complete emitted asset-tree build id", () => {
  const expected = completeTreeBuildId(ASSET_TREE);
  assert.equal(completeAssetTreeBuildId(ASSET_TREE), expected);
  assert.equal(buildId(fs.readFileSync(DRIVER_SW, "utf8")), expected);
  assert.equal(buildId(fs.readFileSync(MASAR_SW, "utf8")), expected);
});

test("the worker build stamps both service workers from one output tree", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "frontend/worker/vite.config.js"),
    "utf8",
  );
  assert.match(
    source,
    /serviceWorkers:\s*\["driver_portal",\s*"worker_portal"\]/,
  );
  const workflow = fs.readFileSync(
    path.join(ROOT, ".github/workflows/portal-bundles.yml"),
    "utf8",
  );
  assert.match(
    workflow,
    /sw:\s*"apex\/www\/masar-sw\.min\.js apex\/www\/driver-sw\.min\.js"/,
  );
});

test("changing only a lazy upload chunk changes the complete-tree build id", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "apex-sw-tree-"));
  fs.mkdirSync(path.join(root, "assets"));
  fs.writeFileSync(path.join(root, "assets/index.js"), "entry");
  fs.writeFileSync(path.join(root, "assets/upload.js"), "old upload");
  const before = completeTreeBuildId(root);
  fs.writeFileSync(path.join(root, "assets/upload.js"), "inline photo upload");
  assert.notEqual(completeTreeBuildId(root), before);
});

test("driver API responses are network-only across a token switch and offline retry", async () => {
  const worker = loadDriverWorker();
  assert.equal(await dispatchFetch(worker, driverApiRequest()), worker.responseA);
  assert.equal(worker.cacheOpenCount(), 0, "driver API response entered a cache");

  worker.setFetchMode("offline");
  await assert.rejects(dispatchFetch(worker, driverApiRequest()), /offline/);
  assert.equal(worker.cacheOpenCount(), 0, "offline driver API read consulted a cache");
});

test("driver activation removes legacy driver data caches without touching Masar", async () => {
  const worker = loadDriverWorker();
  worker.setCacheNames([
    "driver-pwa-v1-old-data",
    "driver-pwa-v1-current-data",
    "masar-pwa-v3-current-data",
  ]);
  let activation;
  worker.handlers.activate({ waitUntil(value) { activation = value; } });
  await activation;
  assert(worker.deletedCaches.includes("driver-pwa-v1-old-data"));
  assert(worker.deletedCaches.includes("driver-pwa-v1-current-data"));
  assert(!worker.deletedCaches.includes("masar-pwa-v3-current-data"));
});

test("a waiting secure driver worker automatically activates and purges vulnerable caches", async () => {
  const worker = loadDriverWorker();
  worker.setCacheNames([
    "driver-pwa-v1-vulnerable-data",
    "driver-pwa-v1-vulnerable-shell",
    "masar-pwa-v3-current-data",
  ]);

  let installation;
  worker.handlers.install({ waitUntil(value) { installation = value; } });
  await installation;
  assert.equal(worker.skipWaitingCount(), 1, "secure driver worker remained waiting");

  let activation;
  worker.handlers.activate({ waitUntil(value) { activation = value; } });
  await activation;
  assert(worker.deletedCaches.includes("driver-pwa-v1-vulnerable-data"));
  assert(worker.deletedCaches.includes("driver-pwa-v1-vulnerable-shell"));
  assert(!worker.deletedCaches.includes("masar-pwa-v3-current-data"));
  assert.equal(worker.claimCount(), 1, "secure worker did not claim existing driver clients");
});
