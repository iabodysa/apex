import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

// Builds the Masar Worker Portal SPA into the app's public assets, served at
// /masar. frappeui() registers the ~icons (lucide) virtual modules frappe-ui
// components use. Output names are stable (un-hashed) so www/masar.html can
// reference them directly.
export default defineConfig({
  plugins: [frappeui(), vue()],
  base: "/assets/apex_habitat/worker_portal/",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: {
    outDir: path.resolve(__dirname, "../public/worker_portal"),
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
