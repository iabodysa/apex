// Copyright (c) 2026, afmcoltd
import { bootstrapPortal } from "@shared/bootstrap.js";
import { IS_DRIVER } from "./holder.js";
import { reconcileServiceWorker } from "./serviceWorkerRegistration.js";

const WORKER_CONFIG = IS_DRIVER
  ? { script: "/driver-sw.min.js", scope: "/driver/" }
  : { script: "/masar-sw.min.js", scope: "/masar/" };

async function registerWorker() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  await reconcileServiceWorker(navigator.serviceWorker, WORKER_CONFIG);
}

async function bootDriver() {
  const [{ default: App }, { default: router }, { initPwa }] = await Promise.all([
    import("../../driver/src/App.vue"),
    import("../../driver/src/router.js"),
    import("../../driver/src/pwa.js"),
  ]);
  await import("../../driver/src/index.css");
  bootstrapPortal({ App, router, setup: () => initPwa() });
}

async function bootWorker() {
  const [{ default: App }, { default: router }] = await Promise.all([
    import("./App.vue"),
    import("./router.js"),
  ]);
  await import("./index.css");
  bootstrapPortal({ App, router });
}

async function start() {
  await (IS_DRIVER ? bootDriver() : bootWorker());
  await registerWorker();
}

start();
