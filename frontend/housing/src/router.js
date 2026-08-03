// Copyright (c) 2026, AFMCO and contributors
import { createRouter, createWebHashHistory } from "vue-router";
import Count from "./pages/Count.vue";
import Delivery from "./pages/Delivery.vue";

const routes = [
  { path: "/", redirect: "/count" },
  { path: "/count", name: "Count", component: Count },
  { path: "/count/:item", name: "CountItem", component: Count },
  { path: "/delivery", name: "Delivery", component: Delivery },
  { path: "/delivery/:name", name: "DeliveryDetail", component: Delivery },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
