// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { configureApi } from "@shared/call";
import router from "./router";
import App from "./App.vue";
import { initPwa } from "./pwa";
import "./index.css";

// [#8jrnfo] wire frappe-ui's resourceFetcher (shared with every portal).
configureApi();

// Capture the browser's install prompt early so the install hint can offer it.
initPwa();

const app = createApp(App);
app.use(router);
app.mount("#app");
