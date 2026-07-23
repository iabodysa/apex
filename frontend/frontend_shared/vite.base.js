// Copyright (c) 2026, AFMCO and contributors
//
// Single Vite config factory for every portal SPA. The five SPA source trees
// live at repo-root frontend/<portal>/ (hrms pattern); this shared factory sits
// beside them at frontend/frontend_shared/. Each portal's vite.config.js is a
// <=15-line call to createPortalConfig(), passing only what actually differs
// between portals (its dirname, package name, and — for the two PWAs — the
// service-worker filename). Everything else (frappe-ui + vue plugins, the dev
// proxy, the @/@shared aliases, the vue/frappe-ui dedupe, the stable un-hashed
// output names) is defined ONCE here so the five configs cannot drift.
//
// Source lives under frontend/<portal>/ but the built bundle MUST still land in
// the Python package at apex/public/<portal>_portal/ so Frappe serves it at the
// unchanged /assets/apex/<portal>_portal/ URL. Hence the ../../apex/... hops
// below reach back out of frontend/ into the apex package.
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";
import fs from "fs";
import { SW_PARAMS } from "./sw.params.js";
import { completeAssetTreeBuildId } from "./sw.build-id.js";
import { renderServiceWorker } from "./sw.template.js";

// After each build, (re)generate each portal service worker from the single
// sw.template.js + its per-portal params, stamping the BUILD marker with a hash of
// the complete freshly emitted asset tree. Both www/*-sw.min.js are single-sourced
// this way: the whole file is emitted here, never hand-edited. The SW is served at the root so
// its scope can cover the portal path, hence it lives outside this app's outDir and
// is written in place. Changing these bytes per build (via the hash) is what makes
// the browser detect an updated worker -> the SPA shows its reload banner. Defined
// once here; only an output tree serving PWAs opts in with `serviceWorkers`.
// The emitted bytes are byte-reconstructable — `node sw.generate.js --check` (the
// portal-tests CI job) verifies committed == render(params, committed-build).
function stampServiceWorkers({ dirname, name, serviceWorkers }) {
  const assetTree = path.resolve(dirname, "../../apex/public/" + name);
  return {
    name: "stamp-sw-" + name,
    closeBundle() {
      try {
        const build = completeAssetTreeBuildId(assetTree);
        for (const workerName of serviceWorkers) {
          const params = SW_PARAMS[workerName];
          if (!params) throw new Error("no service-worker params for portal " + workerName);
          const swPath = path.resolve(dirname, "../../apex/www/" + params.swFilename);
          const rendered = renderServiceWorker({ ...params, build });
          const swSrc = fs.existsSync(swPath) ? fs.readFileSync(swPath, "utf8") : "";
          if (rendered !== swSrc) fs.writeFileSync(swPath, rendered);
        }
      } catch (e) {
        this.error(name + " service-worker stamp failed: " + e.message);
      }
    },
  };
}

// createPortalConfig({ dirname, name, serviceWorkers? }) -> a Vite config identical for all
// portals except base/outDir (derived from `name`) and the optional SW stamp.
//   dirname : the portal's __dirname (its vite.config.js sits at frontend/<portal>/)
//   name    : the portal package dir, e.g. "driver_portal" (drives base + outDir)
//   serviceWorkers : optional SW_PARAMS keys stamped from this complete output tree
export function createPortalConfig({ dirname, name, serviceWorkers }) {
  const plugins = [frappeui(), vue()];
  if (serviceWorkers) {
    plugins.push(stampServiceWorkers({ dirname, name, serviceWorkers }));
  }
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
      // frontend_shared/ AND the folded-in driver screens (the merged Masar portal
      // builds frontend/driver/src from the worker host) live outside the building
      // portal's root and have no node_modules, so their bare imports (frappe-ui, vue,
      // vue-router, socket.io-client) must resolve to the building portal's copy.
      dedupe: ["vue", "vue-router", "frappe-ui", "socket.io-client"],
    },
    build: {
      outDir: path.resolve(dirname, "../../apex/public/" + name),
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
