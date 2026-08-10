// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

import FleetMapView from "./views/FleetMapView.vue";
import HistoryView from "./views/HistoryView.vue";
import PlansView from "./views/PlansView.vue";
import QueueView from "./views/QueueView.vue";

const routes = [
  { path: "/", redirect: "/approvals" },
  { path: "/routes", name: "routes", component: PlansView },
  { path: "/plan/:name/:tab?", name: "plan", component: PlansView },
  { path: "/approvals", name: "approvals", component: QueueView },
  { path: "/map", name: "map", component: FleetMapView },
  { path: "/history", name: "history", component: HistoryView },
  { path: "/:pathMatch(.*)*", redirect: "/approvals" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
