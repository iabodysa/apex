// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { setConfig, frappeRequest } from "frappe-ui";
import App from "./App.vue";
import "./index.css";

// frappe-ui's createResource fetches through frappeRequest, which signs each
// request with window.csrf_token (exposed by www/housing-count.py).
setConfig("resourceFetcher", frappeRequest);

import router from "./router";

createApp(App).use(router).mount("#app");
