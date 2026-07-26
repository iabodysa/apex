// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import App from "./App.vue";
import "./index.css";

// Shared boot: wires frappe-ui's resourceFetcher (also used by src/api.js's
// call()), creates the app, and mounts it. This portal has no router.
//
// [#a281] Byte-identical to fleet_os/src/main.js ON PURPOSE, and it CANNOT be
// shared. This file is the portal's Vite entry: vite.base.js sets
// rollupOptions.input to <portal>/index.html, whose <script src="/src/main.js">
// roots this bundle's whole module graph. The two relative imports resolve to
// DIFFERENT files per portal — ./App.vue is the employee page here and the
// supervisor board in fleet_os, ./index.css is 263 lines of --c-* design-system
// styles here and 1037 lines of legacy supervisor chrome there. Hoisting this
// into @shared would make one module the entry of two separate bundles and bind
// both to one App.vue + one index.css, i.e. it would merge the portals, not
// deduplicate a helper. The behaviour they genuinely share is already in
// @shared/bootstrap.js; what is left is the 3-line per-portal wiring.
bootstrapPortal({ App });
