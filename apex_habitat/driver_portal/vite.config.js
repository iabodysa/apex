import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

// Builds the Driver Portal SPA into the app's public assets, served at /driver.
// frappeui() registers the ~icons (lucide) virtual modules frappe-ui components use.
export default defineConfig({
  plugins: [frappeui(), vue()],
  base: "/assets/apex_habitat/driver_portal/",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: {
    outDir: path.resolve(__dirname, "../public/driver_portal"),
    emptyOutDir: true,
    target: "es2015",
    rollupOptions: {
      input: path.resolve(__dirname, "index.html"),
      // Stable (un-hashed) names so www/driver.html can reference them directly.
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/index[extname]",
      },
    },
  },
});
