import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

// Builds the Fleet OS dashboard SPA into the app's public assets, served at
// /fleet. Output names are stable (un-hashed) so www/fleet.html can reference
// them directly. Mirrors the worker_portal / driver_portal conventions.
export default defineConfig({
  plugins: [vue()],
  base: "/assets/apex_habitat/fleet_portal/",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
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
