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

function builtAssets() {
  const manifest = JSON.parse(fs.readFileSync(path.join(assetTree, ".vite/manifest.json"), "utf8"));
  return [...new Set(Object.values(manifest).flatMap((item) => [item.file, ...(item.css || [])]))]
    .filter((file) => /\.(?:js|css)$/.test(file))
    .map((file) => `${assetBase}/${file}`);
}

export function workerParameters({ assetUrls = builtAssets() } = {}) {
  const common = [
    ...assetUrls,
    "/assets/apex/vendor/thmanyah-v1/thmanyah.css",
    ...fontAssets,
  ];
  return {
    worker: {
      swFilename: "masar-sw.min.js", navPath: "/masar/", scope: "/masar/",
      appId: "/masar/", offlinePath: `${assetBase}/offline.html`,
      immutableAssets: [...common, `${assetBase}/icons/masar-icon-192.png`, `${assetBase}/icons/masar-icon-512.png`, `${assetBase}/icons/masar-apple-touch-icon-180.png`],
      cacheNamespace: "apex:masar:", legacyCachePatterns: ["^masar-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$"],
      skipWaitingOnInstall: false, enablePush: false, push: null,
    },
    driver: {
      swFilename: "driver-sw.min.js", navPath: "/driver/", scope: "/driver/",
      appId: "/driver/", offlinePath: `${assetBase}/offline.html`,
      immutableAssets: [...common, `${assetBase}/icons/driver-icon-192.png`, `${assetBase}/icons/driver-icon-512.png`, `${assetBase}/icons/driver-apple-touch-icon-180.png`],
      cacheNamespace: "apex:driver:", legacyCachePatterns: ["^driver-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$"],
      skipWaitingOnInstall: true, enablePush: true, push: { title: "مسار", tag: "salis-driver" },
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
