// Copyright (c) 2026, AFMCO and contributors
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";
import fs from "fs";
import crypto from "crypto";

// After each build, stamp the service worker's BUILD marker with a hash of the
// built bundle. The SW (served at the root for /driver scope) lives outside this
// app's outDir, so it is patched in place. Changing these bytes per build is what
// makes the browser detect an updated worker -> the SPA shows its reload banner.
function stampServiceWorker() {
  const swPath = path.resolve(__dirname, "../www/driver-sw.min.js");
  const bundlePath = path.resolve(__dirname, "../public/driver_portal/assets/index.js");
  return {
    name: "stamp-driver-sw",
    closeBundle() {
      try {
        const bundle = fs.readFileSync(bundlePath);
        const hash = crypto.createHash("sha256").update(bundle).digest("hex").slice(0, 12);
        const sw = fs.readFileSync(swPath, "utf8");
        const stamped = sw.replace(/const BUILD = "[^"]*";/, `const BUILD = "${hash}";`);
        if (stamped !== sw) fs.writeFileSync(swPath, stamped);
      } catch (e) {
        // Non-fatal: a missing SW just means no update-banner stamping this build.
        this.warn("driver-sw stamp skipped: " + e.message);
      }
    },
  };
}

// [#euj6hi]
export default defineConfig({
  plugins: [frappeui(), vue(), stampServiceWorker()],
  base: "/assets/apex_habitat/driver_portal/",
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
      "@": path.resolve(__dirname, "src"),
      "@shared": path.resolve(__dirname, "../frontend_shared"),
    },
    // frontend_shared/ lives outside this portal's root and has no node_modules,
    // so bare imports there (frappe-ui, vue) must resolve to THIS portal's copy.
    dedupe: ["vue", "frappe-ui"],
  },
  build: {
    outDir: path.resolve(__dirname, "../public/driver_portal"),
    emptyOutDir: true,
    target: "es2015",
    rollupOptions: {
      input: path.resolve(__dirname, "index.html"),
      // [#2imxz2]
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/index[extname]",
      },
    },
  },
});
