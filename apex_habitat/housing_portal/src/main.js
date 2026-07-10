// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import router from "./router";
import App from "./App.vue";
import "./index.css";

// Shared boot: wires frappe-ui's createResource fetcher, creates the app with the
// router, and mounts it.
bootstrapPortal({ App, router });
