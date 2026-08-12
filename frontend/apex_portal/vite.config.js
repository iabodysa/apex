import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import { defineConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));

if (process.env.APEX_PORTAL_REBUILD_VERIFY !== "1") {
  throw new Error("Set APEX_PORTAL_REBUILD_VERIFY=1 for the inactive portal verification build");
}

const outDir = process.env.APEX_PORTAL_VERIFY_OUT_DIR;
if (!outDir || !path.isAbsolute(outDir)) {
  throw new Error("APEX_PORTAL_VERIFY_OUT_DIR must be an absolute temporary directory");
}

export default defineConfig({
  root,
  base: "/assets/apex/portal/",
  plugins: [
    frappeui({
      buildConfig: false,
      frappeProxy: false,
      jinjaBootData: false,
    }),
    vue(),
  ],
  resolve: {
    alias: {
      "@apex-portal": root,
    },
    dedupe: ["vue", "vue-router", "frappe-ui", "socket.io-client"],
  },
  build: {
    outDir,
    emptyOutDir: true,
    manifest: true,
    target: "es2015",
    rollupOptions: { input: path.resolve(root, "index.html") },
  },
});
