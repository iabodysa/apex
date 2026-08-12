import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import { defineConfig } from "vitest/config";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [frappeui({ buildConfig: false, frappeProxy: false, jinjaBootData: false }), vue()],
  resolve: {
    alias: {
      "@apex-portal": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: [
      "**/*.test.mjs",
      "src/**/*.test.mjs",
    ],
    exclude: ["node_modules/**", "dist/**"],
    server: { deps: { inline: ["frappe-ui"] } },
  },
});
