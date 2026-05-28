import { createApp } from "vue";
import { setConfig, frappeRequest } from "frappe-ui";
import router from "./router";
import App from "./App.vue";
import "./index.css";

// frappe-ui resources call Frappe's API (credentials + CSRF handled by frappeRequest).
setConfig("resourceFetcher", frappeRequest);

const app = createApp(App);
app.use(router);
app.mount("#app");
