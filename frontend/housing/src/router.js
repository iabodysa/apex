// Copyright (c) 2026, AFMCO and contributors
import { createRouter, createWebHashHistory } from "vue-router";
import Count from "./pages/Count.vue";
import Delivery from "./pages/Delivery.vue";

const routes = [
  {
    path: "/",
    redirect: "/count",
  },
  {
    path: "/count",
    name: "Count",
    component: Count,
  },
  {
    path: "/delivery",
    name: "Delivery",
    component: Delivery,
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
