// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import App from "./App.vue";
import "./index.css";

// Shared boot: wires frappe-ui's createResource fetcher, creates the app, and
// mounts it. This portal has no router.
bootstrapPortal({ App });
