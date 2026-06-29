// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { setConfig, frappeRequest } from "frappe-ui";
import App from "./App.vue";
import "./index.css";

// frappe-ui's frappeRequest (used by src/api.js's call()) signs each request with
// window.csrf_token (exposed by the www host page); wire it as the fetcher.
setConfig("resourceFetcher", frappeRequest);

createApp(App).mount("#app");
