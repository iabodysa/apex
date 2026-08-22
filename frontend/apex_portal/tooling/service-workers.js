import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { completeAssetTreeBuildId } from "./service-worker-build-id.js";
import { renderServiceWorker } from "./service-worker-template.js";

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(portalRoot, "../..");
const assetTree = path.resolve(repositoryRoot, "apex/public/apex_portal");
const www = path.resolve(repositoryRoot, "apex/www");
const assetBase = "/assets/apex/apex_portal";
const fontAssets = ["Light", "Regular", "Medium", "Bold", "Black"].flatMap((weight) => [
  `/assets/apex/vendor/thmanyah-v1/thmanyahsans-${weight}.woff2`,
  `/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-${weight}.woff2`,
  `/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-${weight}.woff2`,
]);

/**
 * The js and css a portal loads before its router resolves any route.
 *
 * Walks the Vite manifest from the single rollup input (vite.config.js:52) following static
 * `imports` only. A chunk listed under `dynamicImports` is reached by a `() => import()` inside
 * one feature's routes.js, and `createPortalRouter`
 * (frontend/apex_portal/core/router.js:66) hands a context only the routes whose `feature` that
 * context declares — so a context that declares none of those features can never fire the import.
 * Following `dynamicImports` here would precache every other context's pages.
 *
 * Masar and the driver portal declare only `worker` and `driver` respectively
 * (core/router.js:28-33), and neither features/worker/routes.js nor features/driver/routes.js
 * holds a dynamic import, so this closure is their complete asset set. Adding a dynamic import
 * to either feature breaks that and this walk must then follow it.
 *
 * @param {string} entry the manifest key of the rollup input
 * @returns {string[]} absolute asset URLs, deduplicated
 */
function entryAssets(entry = "index.html") {
  const manifest = JSON.parse(fs.readFileSync(path.join(assetTree, ".vite/manifest.json"), "utf8"));
  const reached = new Set();
  const walk = (key) => {
    if (reached.has(key)) return;
    reached.add(key);
    for (const dependency of manifest[key].imports || []) walk(dependency);
  };
  walk(entry);
  return [...new Set([...reached].flatMap((key) => [manifest[key].file, ...(manifest[key].css || [])]))]
    .filter((file) => /\.(?:js|css)$/.test(file))
    .map((file) => `${assetBase}/${file}`);
}

export function workerParameters({ assetUrls = entryAssets() } = {}) {
  // Every URL here carries its own version: a Vite content hash in the filename, or the
  // `thmanyah-v1` directory for the vendored cuts. A URL that survives a deploy names the same
  // bytes, which is what lets the worker keep its cached copy across builds. Moving a
  // stable-URL file into this list would serve its stale body forever.
  const durable = [
    ...assetUrls,
    "/assets/apex/vendor/thmanyah-v1/thmanyah.css",
    ...fontAssets,
  ];
  return {
    worker: {
      swFilename: "masar-sw.min.js", navPath: "/masar/", scope: "/masar/",
      appId: "/masar/", offlinePath: `${assetBase}/offline.html`,
      durableAssets: durable,
      versionedAssets: [`${assetBase}/offline.css`, `${assetBase}/icons/masar-icon-192.png`, `${assetBase}/icons/masar-icon-maskable-512.png`, `${assetBase}/icons/masar-apple-touch-icon-180.png`],
      cacheNamespace: "apex:masar:", legacyCachePatterns: ["^masar-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$"],
      skipWaitingOnInstall: false,
      enablePush: true,
      push: { title: "مسار", tag: "masar-worker", icon: `${assetBase}/icons/masar-icon-192.png` },
    },
    driver: {
      swFilename: "driver-sw.min.js", navPath: "/driver/", scope: "/driver/",
      appId: "/driver/", offlinePath: `${assetBase}/offline.html`,
      durableAssets: durable,
      versionedAssets: [`${assetBase}/offline.css`, `${assetBase}/icons/driver-icon-192.png`, `${assetBase}/icons/driver-icon-maskable-512.png`, `${assetBase}/icons/driver-apple-touch-icon-180.png`],
      cacheNamespace: "apex:driver:", legacyCachePatterns: ["^driver-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$"],
      skipWaitingOnInstall: true,
      enablePush: true,
      push: { title: "مسار", tag: "salis-driver", icon: `${assetBase}/icons/driver-icon-192.png` },
    },
  };
}

export function generateServiceWorkers({ write = false } = {}) {
  const build = completeAssetTreeBuildId(assetTree);
  let valid = true;
  for (const params of Object.values(workerParameters())) {
    const target = path.join(www, params.swFilename);
    const rendered = renderServiceWorker({ ...params, build });
    const current = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : "";
    if (write) fs.writeFileSync(target, rendered);
    else valid = valid && current === rendered && Boolean(current);
    console.log(`${write ? "WROTE" : current === rendered ? "OK" : "FAIL"} ${params.swFilename} (${build})`);
  }
  return valid;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.env.APEX_PORTAL_REBUILD_VERIFY === "1") {
    console.log("SKIP service workers during verification build");
    process.exit(0);
  }
  const write = process.argv.includes("--write");
  if (!generateServiceWorkers({ write })) process.exitCode = 1;
}
