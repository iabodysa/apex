// Copyright (c) 2026, afmcoltd
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";
import fs from "fs";
import { SW_PARAMS } from "./sw.params.js";
import { completeAssetTreeBuildId } from "./sw.build-id.js";
import { renderServiceWorker } from "./sw.template.js";

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

const INERT_INDEX_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="robots" content="noindex" />
    <title>Apex portal bundle</title>
  </head>
  <body>
    <p>Built portal assets. The application is served by its own web route, which checks access first.</p>
  </body>
</html>
`;

function inertIndexHtml() {
  return {
    name: "apex-inert-index-html",
    apply: "build",
    enforce: "post",
    transformIndexHtml() {
      return INERT_INDEX_HTML;
    },
  };
}

export function createPortalConfig({ dirname, name, serviceWorkers }) {
  const plugins = [frappeui({ jinjaBootData: false }), vue(), inertIndexHtml()];
  if (serviceWorkers) {
    plugins.push(stampServiceWorkers({ dirname, name, serviceWorkers }));
  }
  return defineConfig({
    plugins,
    base: "/assets/apex/" + name + "/",
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
