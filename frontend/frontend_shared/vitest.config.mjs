// Copyright (c) 2026, AFMCO and contributors
// Vitest config for the shared portal components. Mirrors the aliases the real
// portal builds provide (@shared -> this dir; @ -> a test fixtures dir that stands
// in for "the consuming portal's src", supplying a fake i18n + Icon). jsdom lets us
// mount the .vue components and assert their rendered DOM.
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import path from "path";

const here = path.dirname(new URL(import.meta.url).pathname);

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@shared": path.resolve(here),
      // Stands in for the consuming portal's own src/ (@/i18n, @/components/Icon.vue).
      "@": path.resolve(here, "components/__tests__/fixtures"),
      // Stub the frappe-ui resource layer so components mount without a backend.
      "frappe-ui": path.resolve(here, "components/__tests__/fixtures/frappe-ui.js"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/__tests__/**/*.test.mjs"],
  },
});
