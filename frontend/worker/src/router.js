// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./pages/Home.vue") },
  { path: "/profile", name: "profile", component: () => import("./pages/Profile.vue") },
  { path: "/accommodation", name: "accommodation", component: () => import("./pages/Accommodation.vue") },
  { path: "/transport", name: "transport", component: () => import("./pages/Transport.vue") },
  { path: "/request-transport", name: "request-transport", component: () => import("./pages/RequestTransport.vue") },
  { path: "/custody", name: "custody", component: () => import("./pages/Custody.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
  { path: "/requests/:name", name: "request-detail", component: () => import("./pages/RequestDetail.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
