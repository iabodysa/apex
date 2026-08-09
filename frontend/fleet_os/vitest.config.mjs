// Copyright (c) 2026, afmcoltd
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

const here = path.dirname(new URL(import.meta.url).pathname);

export default defineConfig({
  root: here,
  plugins: [frappeui({ jinjaBootData: false }), vue()],
  resolve: {
    alias: {
      "@shared": path.resolve(here, "../frontend_shared"),
      "@": path.resolve(here, "src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/__tests__/**/*.test.mjs"],
    server: { deps: { inline: ["frappe-ui"] } },
  },
});
