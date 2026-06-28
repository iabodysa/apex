// Copyright (c) 2026, AFMCO and contributors
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

// [#cynnk9]
export default defineConfig({
  plugins: [vue()],
  base: "/assets/apex_habitat/fleet_portal/",
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
