// Copyright (c) 2026, AFMCO and contributors
import { bootstrapPortal } from "@shared/bootstrap.js";
import App from "./App.vue";
import "./index.css";

// Shared boot: wires frappe-ui's resourceFetcher (also used by src/api.js's call()),
// creates the app, and mounts it. Single-view portal — no router.
bootstrapPortal({ App });
