// Copyright (c) 2026, AFMCO and contributors
// Real pages, mirroring the worker/driver portals' router idiom: hash history
// (the /fleet www route serves one HTML shell, so no server-side route is
// needed) and a catch-all redirect home.
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
