// Copyright (c) 2026, AFMCO and contributors
// Vitest config for the shared portal components. Mirrors the aliases the real
// portal builds provide (@shared -> this dir; @ -> a test fixtures dir that stands
// in for "the consuming portal's src", supplying a fake i18n + Icon). jsdom lets us
// mount the .vue components and assert their rendered DOM.
//
// frappe-ui is deliberately NOT aliased. A whole-package stub made every library
// control resolve to undefined in any mounted portal, so a suite asserting on a
// FormControl the portal really renders failed for a reason that had nothing to do
// with the portal. The one part that needs a backend, createListResource, is mocked
// per-suite instead.
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import path from "path";

const here = path.dirname(new URL(import.meta.url).pathname);

export default defineConfig({
  plugins: [frappeui({ jinjaBootData: false }), vue()],
  resolve: {
    alias: {
      "@shared": path.resolve(here),
      // Stands in for the consuming portal's own src/ (@/i18n, @/components/Icon.vue).
      "@": path.resolve(here, "components/__tests__/fixtures"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/__tests__/**/*.test.mjs"],
    server: {
      // frappe-ui ships its own uncompiled src, where imports carry no file
      // extension. Node's ESM resolver refuses those; Vite's does not. Inlining
      // routes the package through the same transform the portal builds use.
      deps: { inline: ["frappe-ui"] },
    },
  },
});
