// Copyright (c) 2026, afmcoltd
import { bootstrapPortal } from "@shared/bootstrap.js";
import App from "./app/App.vue";
import router from "./app/router.js";
import "./index.css";

bootstrapPortal({ App, router });
