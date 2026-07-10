// Copyright (c) 2026, AFMCO and contributors
import { createApp } from "vue";
import { configureApi } from "@shared/call";
import router from "./router";
import App from "./App.vue";
import "./index.css";

// [#8jrnfo] wire frappe-ui's resourceFetcher (shared with every portal).
configureApi();

const app = createApp(App);
app.use(router);
app.mount("#app");
