// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import router from "./router";
import App from "./App.vue";
import { initPwa } from "./pwa";
import "./index.css";

// [#8jrnfo] shared boot: wires frappe-ui's resourceFetcher, creates the app with
// the router, and mounts it. `setup` captures the browser's install prompt early
// (via initPwa) so the install hint can offer it.
bootstrapPortal({ App, router, setup: () => initPwa() });
