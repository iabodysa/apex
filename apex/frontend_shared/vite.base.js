// Copyright (c) 2026, AFMCO and contributors
//
// Single Vite config factory for every *_portal SPA. Each portal's
// vite.config.js is a <=15-line call to createPortalConfig(), passing only what
// actually differs between portals (its dirname, package name, and — for the two
// PWAs — the service-worker filename). Everything else (frappe-ui + vue plugins,
// the dev proxy, the @/@shared aliases, the vue/frappe-ui dedupe, the stable
// un-hashed output names) is defined ONCE here so the five configs cannot drift.
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";
import fs from "fs";
import crypto from "crypto";

// After each build, stamp the service worker's BUILD marker with a hash of the
// built bundle. The SW (served at the root so its scope can cover the portal
// path) lives outside this app's outDir, so it is patched in place. Changing
// these bytes per build is what makes the browser detect an updated worker ->
// the SPA shows its reload banner. Defined once here; only the two PWA portals
// (driver, worker) opt in by passing `sw`.
function stampServiceWorker({ dirname, name, sw }) {
  const swPath = path.resolve(dirname, "../www/" + sw);
  const bundlePath = path.resolve(dirname, "../public/" + name + "/assets/index.js");
  return {
    name: "stamp-sw-" + name,
    closeBundle() {
      try {
        const bundle = fs.readFileSync(bundlePath);
        const hash = crypto.createHash("sha256").update(bundle).digest("hex").slice(0, 12);
        const swSrc = fs.readFileSync(swPath, "utf8");
        const stamped = swSrc.replace(/const BUILD = "[^"]*";/, `const BUILD = "${hash}";`);
        if (stamped !== swSrc) fs.writeFileSync(swPath, stamped);
      } catch (e) {
        // Non-fatal: a missing SW just means no update-banner stamping this build.
        this.warn(name + " sw stamp skipped: " + e.message);
      }
    },
  };
}

// createPortalConfig({ dirname, name, sw? }) -> a Vite config identical for all
// portals except base/outDir (derived from `name`) and the optional SW stamp.
//   dirname : the portal's __dirname (its vite.config.js sits in the portal root)
//   name    : the portal package dir, e.g. "driver_portal" (drives base + outDir)
//   sw      : optional www SW filename to stamp, e.g. "driver-sw.min.js"
export function createPortalConfig({ dirname, name, sw }) {
  const plugins = [frappeui(), vue()];
  if (sw) plugins.push(stampServiceWorker({ dirname, name, sw }));
  return defineConfig({
    plugins,
    base: "/assets/apex/" + name + "/",
    // Dev-only: proxy API/asset calls to the local Frappe bench so `vite dev` can
    // reach the backend. No effect on the production build.
    server: {
      proxy: {
        "/api": "http://localhost:8000",
        "/assets": "http://localhost:8000",
        "/files": "http://localhost:8000",
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(dirname, "src"),
        "@shared": path.resolve(dirname, "../frontend_shared"),
      },
      // frontend_shared/ lives outside each portal's root and has no node_modules,
      // so bare imports there (frappe-ui, vue, socket.io-client used by the shared
      // realtime factory) must resolve to the importing portal's copy.
      dedupe: ["vue", "frappe-ui", "socket.io-client"],
    },
    build: {
      outDir: path.resolve(dirname, "../public/" + name),
      emptyOutDir: true,
      target: "es2015",
      rollupOptions: {
        input: path.resolve(dirname, "index.html"),
        output: {
          entryFileNames: "assets/index.js",
          chunkFileNames: "assets/[name].js",
          assetFileNames: "assets/index[extname]",
        },
      },
    },
  });
}
