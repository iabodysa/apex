// Copyright (c) 2026, AFMCO and contributors
//
// Merged Masar portal entry — ONE bundle for BOTH holder types. The two passwordless
// barcode entries (/masar for workers, /driver for drivers) load this same built
// bundle; the www template projects window.holder_type and ./holder.js reads it, so
// this entry mounts only the chosen type's app:
//   - Worker -> frontend/worker/src (App + router + pages + i18n), the Masar screens.
//   - Driver -> frontend/driver/src (App + router + pages + i18n), the driver screens.
// Both mount the shared MobileConsoleShell via the shared bootstrapPortal, so this is
// a packaging merge, not a screen rewrite — every existing screen, Arabic copy, and
// per-type API call is reused verbatim from its source tree. Each type is dynamically
// imported into its own chunk, so a worker never downloads driver JS and vice-versa.
import { bootstrapPortal } from "@shared/bootstrap.js";
import { IS_DRIVER } from "./holder.js";

async function boot() {
  if (IS_DRIVER) {
    // Driver screens live in the sibling source tree; relative imports inside those
    // files still resolve against frontend/driver/src (per-file relative), and their
    // @shared alias resolves to the same frontend_shared as the worker build.
    const [{ default: App }, { default: router }, { initPwa }] = await Promise.all([
      import("../../driver/src/App.vue"),
      import("../../driver/src/router.js"),
      import("../../driver/src/pwa.js"),
    ]);
    await import("../../driver/src/index.css");
    bootstrapPortal({ App, router, setup: () => initPwa() });
  } else {
    const [{ default: App }, { default: router }] = await Promise.all([
      import("./App.vue"),
      import("./router.js"),
    ]);
    await import("./index.css");
    bootstrapPortal({ App, router });
  }
}

boot();
