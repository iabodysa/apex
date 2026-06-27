import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

// Mirrors safety_portal's config; only the name/paths differ so the housing
// count portal builds to its own stable, un-hashed bundle.
export default defineConfig({
  plugins: [frappeui(), vue()],
  base: "/assets/apex_habitat/housing_portal/",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: {
    outDir: path.resolve(__dirname, "../public/housing_portal"),
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
