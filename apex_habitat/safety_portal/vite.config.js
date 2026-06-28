// Copyright (c) 2026, AFMCO and contributors
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

// Mirrors worker_portal's config; only the name/paths differ so the safety
// portal builds to its own stable, un-hashed bundle.
export default defineConfig({
  plugins: [frappeui(), vue()],
  base: "/assets/apex_habitat/safety_portal/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@shared": path.resolve(__dirname, "../frontend_shared"),
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../public/safety_portal"),
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
