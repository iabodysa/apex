// Copyright (c) 2026, afmcoltd

const THMANYAH_OFFLINE_ASSETS = Object.freeze([
  "/assets/apex/vendor/thmanyah-v1/thmanyah.css",
  "/assets/apex/vendor/thmanyah-v1/thmanyahsans-Light.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-Light.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-Light.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahsans-Regular.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-Regular.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-Regular.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahsans-Medium.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-Medium.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-Medium.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahsans-Bold.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-Bold.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-Bold.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahsans-Black.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahserifdisplay-Black.woff2",
  "/assets/apex/vendor/thmanyah-v1/thmanyahseriftext-Black.woff2",
]);

export const SW_PARAMS = {
  driver_portal: {
    displayName: "Masar",
    swFilename: "driver-sw.min.js",
    navPath: "/driver",
    assetBase: "/assets/apex/worker_portal",
    cacheVersion: "driver-pwa-v1-",
    cacheNamespace: "driver-pwa-",
    cacheData: false,
    skipWaitingOnInstall: true,
    networkOnlyApiPrefixes: [
      "/api/method/apex.salis.api.driver_portal.",
      "/api/method/apex.salis.api.boarding.",
      "/api/method/apex.salis.api.boarding_flow.",
    ],
    offlineAssets: THMANYAH_OFFLINE_ASSETS,
    enablePush: true,
    push: { title: "Masar", tag: "salis-driver" },
  },

  worker_portal: {
    displayName: "Masar",
    swFilename: "masar-sw.min.js",
    navPath: "/masar",
    assetBase: "/assets/apex/worker_portal",
    cacheVersion: "masar-pwa-v4-",
    cacheNamespace: "masar-pwa-",
    cacheData: false,
    skipWaitingOnInstall: true,
    networkOnlyApiPrefixes: [
      "/api/method/apex.salis.api.masar.",
      "/api/method/apex.salis.api.masar_worker.",
      "/api/method/apex.salis.api.boarding_flow.",
    ],
    offlineAssets: THMANYAH_OFFLINE_ASSETS,
    enablePush: false,
    push: null,
  },
};
