import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import { defineConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { sealPublicIndex } from "./tooling/seal-public-index.js";

const root = fileURLToPath(new URL(".", import.meta.url));
const repositoryRoot = path.resolve(root, "../..");
const verification = process.env.APEX_PORTAL_REBUILD_VERIFY === "1";
const outDir = verification
  ? process.env.APEX_PORTAL_VERIFY_OUT_DIR
  : path.resolve(repositoryRoot, "apex/public/apex_portal");
const indexHtmlPath = verification
  ? process.env.APEX_PORTAL_VERIFY_INDEX_PATH
  : path.resolve(repositoryRoot, "apex/templates/includes/apex_portal_app.html");

if (!outDir || !path.isAbsolute(outDir)) {
  throw new Error("APEX_PORTAL_VERIFY_OUT_DIR must be an absolute temporary directory");
}
if (!indexHtmlPath || !path.isAbsolute(indexHtmlPath)) {
  throw new Error("APEX_PORTAL_VERIFY_INDEX_PATH must be an absolute temporary file");
}

export default defineConfig({
  root,
  plugins: [
    frappeui({
      buildConfig: {
        outDir,
        indexHtmlPath,
        baseUrl: "/assets/apex/apex_portal/",
        sourcemap: false,
      },
      frappeProxy: false,
      jinjaBootData: false,
    }),
    vue(),
    sealPublicIndex({ outDir }),
  ],
  resolve: {
    alias: {
      "@apex-portal": root,
    },
    dedupe: ["vue", "vue-router", "frappe-ui", "socket.io-client"],
  },
  build: {
    manifest: true,
    sourcemap: false,
    target: "es2015",
    rollupOptions: {
      input: path.resolve(root, "index.html"),
      output: {
        manualChunks: {
          "vue-runtime": ["vue", "vue-router"],
          "frappe-ui-runtime": ["frappe-ui"],
        },
      },
    },
  },
});
