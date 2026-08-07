// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import App from "./App.vue";
import router from "./router.js";
import "./index.css";

// Shared boot: wires frappe-ui's resourceFetcher (also used by src/api.js's
// call()), creates the app, installs the router, and mounts it.
//
// [#a281] This file is the portal's Vite entry: vite.base.js sets
// rollupOptions.input to <portal>/index.html, whose <script src="/src/main.js">
// roots this bundle's whole module graph. The relative imports resolve to
// DIFFERENT files per portal — ./App.vue is the employee page here and the
// supervisor board in fleet_os. Hoisting this into @shared would make one
// module the entry of two separate bundles, i.e. it would merge the portals,
// not deduplicate a helper. The behaviour they genuinely share is already in
// @shared/bootstrap.js; what is left is the per-portal wiring.
bootstrapPortal({ App, router });
