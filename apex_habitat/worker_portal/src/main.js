// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import router from "./router";
import App from "./App.vue";
import "./index.css";

// [#8jrnfo] shared boot: wires frappe-ui's resourceFetcher, creates the app with
// the router, and mounts it.
bootstrapPortal({ App, router });
