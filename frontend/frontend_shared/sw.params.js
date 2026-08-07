// Copyright (c) 2026, afmcoltd

export const SW_PARAMS = {
  driver_portal: {
    displayName: "Salis Driver",
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
    fonts: [],
    enablePush: true,
    push: { title: "Salis Driver", tag: "salis-driver" },
  },

  worker_portal: {
    displayName: "Masar",
    swFilename: "masar-sw.min.js",
    navPath: "/masar",
    assetBase: "/assets/apex/worker_portal",
    cacheVersion: "masar-pwa-v3-",
    cacheNamespace: "masar-pwa-",
    cacheData: true,
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
    fonts: [
      "cairo-arabic",
      "cairo-latin",
      "cairo-latin-ext",
      "montserrat-latin",
      "montserrat-latin-ext",
    ],
    enablePush: false,
    push: null,
  },
};
