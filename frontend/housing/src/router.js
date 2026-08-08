// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";
import { hasSection } from "./portal.js";
import { landingPath } from "./sections.js";
import Arrivals from "./pages/Arrivals.vue";
import Beds from "./pages/Beds.vue";
import Count from "./pages/Count.vue";
import Custody from "./pages/Custody.vue";
import Delivery from "./pages/Delivery.vue";
import NoAccess from "./pages/NoAccess.vue";
import Round from "./pages/Round.vue";
import Transfer from "./pages/Transfer.vue";

const routes = [
  { path: "/", redirect: () => landingPath() },
  { path: "/count", name: "Count", component: Count, meta: { section: "count" } },
  { path: "/count/:item", name: "CountItem", component: Count, meta: { section: "count" } },
  { path: "/delivery", name: "Delivery", component: Delivery, meta: { section: "delivery" } },
  {
    path: "/delivery/:name",
    name: "DeliveryDetail",
    component: Delivery,
    meta: { section: "delivery" },
  },
  { path: "/beds", name: "Beds", component: Beds, meta: { section: "beds" } },
  { path: "/beds/:bed", name: "BedDetail", component: Beds, meta: { section: "beds" } },
  { path: "/arrivals", name: "Arrivals", component: Arrivals, meta: { section: "arrivals" } },
  { path: "/custody", name: "Custody", component: Custody, meta: { section: "custody" } },
  { path: "/transfer", name: "Transfer", component: Transfer, meta: { section: "transfer" } },
  { path: "/safety", name: "Round", component: Round, meta: { section: "safety" } },
  { path: "/no-access", name: "NoAccess", component: NoAccess },
  { path: "/:pathMatch(.*)*", redirect: () => landingPath() },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const section = to.meta && to.meta.section;
  if (section && !hasSection(section)) return { path: "/no-access" };
  return true;
});

export default router;
