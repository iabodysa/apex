import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "profile", component: () => import("./pages/Profile.vue") },
  { path: "/accommodation", name: "accommodation", component: () => import("./pages/Accommodation.vue") },
  { path: "/transport", name: "transport", component: () => import("./pages/Transport.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
];

export default createRouter({ history: createWebHashHistory(), routes });
