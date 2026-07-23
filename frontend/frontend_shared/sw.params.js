// Copyright (c) 2026, AFMCO and contributors
//
// Per-portal params for the two PWA service workers, keyed by the portal package
// name (the `name` the vite factory passes, which is also the apex/public/<name>
// output dir). Consumed by sw.template.js (renderServiceWorker) via both the
// stampServiceWorker vite plugin and the standalone sw.generate.js.
//
// Every field here is a REAL behavioural difference between the two workers; the
// shared caching logic lives once in sw.template.js. `build` is NOT stored here —
// it is the bundle content-hash, injected per build (plugin) or carried forward
// from the committed file (standalone regen).

export const SW_PARAMS = {
  driver_portal: {
    displayName: "Salis Driver",
    swFilename: "driver-sw.min.js",
    navPath: "/driver",
    // Merged Masar portal: /driver now serves the SHARED worker_portal bundle, so the
    // driver PWA precaches and offline-serves that bundle (its own driver_portal build
    // is retired). navPath stays /driver (its own scope + push), only the asset base
    // moves to the one merged output dir.
    assetBase: "/assets/apex/worker_portal",
    // v1 cache generation for the driver PWA. Bump the digit to force a full
    // cache reset for installed drivers independently of the worker PWA.
    cacheVersion: "driver-pwa-v1-",
    cacheNamespace: "driver-pwa-",
    cacheData: false,
    // Driver security updates must take control without user interaction.
    skipWaitingOnInstall: true,
    networkOnlyApiPrefixes: [
      "/api/method/apex.salis.api.driver_portal.",
      "/api/method/apex.salis.api.boarding.",
      "/api/method/apex.salis.api.boarding_flow.",
    ],
    // Driver fonts load from a CDN (not self-hosted): no precache, no cache-first.
    fonts: [],
    // Driver ships Web Push (opt-in + VAPID-gated); the worker PWA does not.
    enablePush: true,
    push: { title: "Salis Driver", tag: "salis-driver" },
  },

  worker_portal: {
    displayName: "Masar",
    swFilename: "masar-sw.min.js",
    navPath: "/masar",
    assetBase: "/assets/apex/worker_portal",
    // v3 cache generation for the worker (masar) PWA — ahead of driver's v1
    // because masar reset its caches twice more during earlier rollouts.
    cacheVersion: "masar-pwa-v3-",
    cacheNamespace: "masar-pwa-",
    cacheData: true,
    // Masar keeps the existing user-confirmed reload-banner lifecycle.
    skipWaitingOnInstall: false,
    dataCacheHost: "masar-data",
    dataEndpoints: [
      "/api/method/apex.salis.api.masar.get_worker_context",
      "/api/method/apex.salis.api.masar.get_worker_home",
      "/api/method/apex.salis.api.masar.get_worker_accommodation",
      "/api/method/apex.salis.api.masar.get_worker_transport",
      "/api/method/apex.salis.api.masar.get_worker_custody",
      "/api/method/apex.salis.api.masar.get_worker_request_detail",
    ],
    networkOnlyApiPrefixes: [],
    // Masar self-hosts its fonts: precache them AND serve them cache-first.
    fonts: [
      "cairo-arabic",
      "cairo-latin",
      "cairo-latin-ext",
      "montserrat-latin",
      "montserrat-latin-ext",
    ],
    // No Web Push on the worker PWA.
    enablePush: false,
    push: null,
  },
};
