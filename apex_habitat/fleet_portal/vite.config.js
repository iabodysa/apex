// Copyright (c) 2026, AFMCO and contributors
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

// [#cynnk9]
export default defineConfig({
  plugins: [frappeui(), vue()],
  base: "/assets/apex_habitat/fleet_portal/",
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
  },
  build: {
    outDir: path.resolve(__dirname, "../public/fleet_portal"),
    emptyOutDir: true,
    target: "es2015",
    rollupOptions: {
      input: path.resolve(__dirname, "index.html"),
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/index[extname]",
      },
    },
  },
});
