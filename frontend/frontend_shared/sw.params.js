const ASSET_BASE = "/assets/apex/worker_portal";

const THMANYAH_ASSETS = Object.freeze([
  "/assets/apex/vendor/thmanyah-v1/thmanyah.css",
  ...["Light", "Regular", "Medium", "Bold", "Black"].flatMap((weight) => [
    `/assets/apex/vendor/thmanyah-v1/thmanyahsans-${weight}.woff2`,
    `/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-${weight}.woff2`,
    `/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-${weight}.woff2`,
  ]),
]);

const SHARED_ASSETS = Object.freeze([
  `${ASSET_BASE}/assets/index.js`,
  `${ASSET_BASE}/assets/index.css`,
  ...THMANYAH_ASSETS,
]);

export const SW_PARAMS = Object.freeze({
  driver_portal: Object.freeze({
    displayName: "Masar",
    swFilename: "driver-sw.min.js",
    navPath: "/driver/",
    scope: "/driver/",
    appId: "/driver/",
    offlinePath: `${ASSET_BASE}/offline.html`,
    immutableAssets: Object.freeze([
      ...SHARED_ASSETS,
      `${ASSET_BASE}/icons/driver-icon-192.png`,
      `${ASSET_BASE}/icons/driver-icon-512.png`,
      `${ASSET_BASE}/icons/driver-apple-touch-icon-180.png`,
    ]),
    cacheNamespace: "apex:driver:",
    legacyCachePatterns: Object.freeze([
      "^driver-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$",
    ]),
    skipWaitingOnInstall: true,
    enablePush: true,
    push: Object.freeze({ title: "Masar", tag: "salis-driver" }),
  }),

  worker_portal: Object.freeze({
    displayName: "Masar",
    swFilename: "masar-sw.min.js",
    navPath: "/masar/",
    scope: "/masar/",
    appId: "/masar/",
    offlinePath: `${ASSET_BASE}/offline.html`,
    immutableAssets: Object.freeze([
      ...SHARED_ASSETS,
      `${ASSET_BASE}/icons/masar-icon-192.png`,
      `${ASSET_BASE}/icons/masar-icon-512.png`,
      `${ASSET_BASE}/icons/masar-apple-touch-icon-180.png`,
    ]),
    cacheNamespace: "apex:masar:",
    legacyCachePatterns: Object.freeze([
      "^masar-pwa-v[0-9]+-[a-f0-9]{12}-(?:shell|data)$",
    ]),
    skipWaitingOnInstall: false,
    enablePush: false,
    push: null,
  }),
});
