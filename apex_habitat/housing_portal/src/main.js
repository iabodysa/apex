// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { configureApi } from "@shared/call";
import App from "./App.vue";
import "./index.css";

// Wire frappe-ui's createResource fetcher (frappeRequest signs each request with
// window.csrf_token, exposed by www/housing-count.py). Shared with every portal.
configureApi();

import router from "./router";

createApp(App).use(router).mount("#app");
