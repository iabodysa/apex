// Copyright (c) 2026, afmcoltd
import { bootstrapPortal } from "@shared/bootstrap.js";
import router from "./router";
import App from "./App.vue";
import "./index.css";

bootstrapPortal({ App, router });
