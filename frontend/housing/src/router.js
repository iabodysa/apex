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
import Today from "./pages/Today.vue";
import Transfer from "./pages/Transfer.vue";

const routes = [
  { path: "/", redirect: () => landingPath() },
  { path: "/today", name: "Today", component: Today, meta: { section: "today", domain: "today" } },
  {
    path: "/count",
    name: "Count",
    component: Count,
    meta: { section: "count", domain: "assets" },
  },
  {
    path: "/count/:item",
    name: "CountItem",
    component: Count,
    meta: { section: "count", domain: "assets" },
  },
  {
    path: "/delivery",
    name: "Delivery",
    component: Delivery,
    meta: { section: "delivery", domain: "assets" },
  },
  {
    path: "/delivery/:name",
    name: "DeliveryDetail",
    component: Delivery,
    meta: { section: "delivery", domain: "assets" },
  },
  {
    path: "/beds",
    name: "Beds",
    component: Beds,
    meta: { section: "beds", domain: "residents" },
  },
  {
    path: "/beds/:bed",
    name: "BedDetail",
    component: Beds,
    meta: { section: "beds", domain: "residents" },
  },
  {
    path: "/arrivals",
    name: "Arrivals",
    component: Arrivals,
    meta: { section: "arrivals", domain: "residents" },
  },
  {
    path: "/custody",
    name: "Custody",
    component: Custody,
    meta: { section: "custody", domain: "assets" },
  },
  {
    path: "/transfer",
    name: "Transfer",
    component: Transfer,
    meta: { section: "transfer", domain: "residents" },
  },
  {
    path: "/safety",
    name: "Round",
    component: Round,
    meta: { section: "safety", domain: "safety" },
  },
  { path: "/no-access", name: "NoAccess", component: NoAccess },
  { path: "/:pathMatch(.*)*", redirect: () => landingPath() },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const section = to.meta && to.meta.section;
  if (section === "today") {
    const target = landingPath();
    if (target !== "/today") return { path: target };
    return true;
  }
  if (section && !hasSection(section)) return { path: "/no-access" };
  return true;
});

export default router;
