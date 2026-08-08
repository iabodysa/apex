// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

import FuelView from "./views/FuelView.vue";
import HomeView from "./views/HomeView.vue";
import TripsView from "./views/TripsView.vue";

/* Three addresses, hash history, anything else home. Statically imported because the page
   template links exactly one stylesheet, so a lazily loaded screen would have to inject its
   own at runtime. */
const routes = [
  { path: "/", name: "home", component: HomeView },
  { path: "/trips", name: "trips", component: TripsView },
  { path: "/fuel", name: "fuel", component: FuelView },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
