// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./pages/Home.vue") },
  { path: "/trips", name: "trips", component: () => import("./pages/Trips.vue") },
  { path: "/fuel", name: "fuel", component: () => import("./pages/Fuel.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
