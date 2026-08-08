// Copyright (c) 2026, afmcoltd
import { bootstrapPortal } from "@shared/bootstrap.js";
import { IS_DRIVER } from "./holder.js";

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

(IS_DRIVER ? bootDriver() : bootWorker());
