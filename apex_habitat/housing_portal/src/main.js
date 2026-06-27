import { createApp } from "vue";
import { setConfig, frappeRequest } from "frappe-ui";
import App from "./App.vue";
import "./index.css";

// frappe-ui's createResource fetches through frappeRequest, which signs each
// request with window.csrf_token (exposed by www/housing-count.py).
setConfig("resourceFetcher", frappeRequest);

createApp(App).mount("#app");
