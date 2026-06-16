import { createApp } from "vue";
import { setConfig, frappeRequest } from "frappe-ui";
import router from "./router";
import App from "./App.vue";
import "./index.css";

// [#8jrnfo]
setConfig("resourceFetcher", frappeRequest);

const app = createApp(App);
app.use(router);
app.mount("#app");
