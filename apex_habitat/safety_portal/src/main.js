// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { configureApi } from "@shared/call";
import App from "./App.vue";
import "./index.css";

// Wire frappe-ui's createResource fetcher (frappeRequest signs each request with
// window.csrf_token, exposed by www/safety.py). Shared with every portal.
configureApi();

createApp(App).mount("#app");
