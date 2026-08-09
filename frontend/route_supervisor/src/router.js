// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

import FleetMapView from "./views/FleetMapView.vue";
import HistoryView from "./views/HistoryView.vue";
import PlansView from "./views/PlansView.vue";
import QueueView from "./views/QueueView.vue";

/* Every screen of this portal is addressable, and the address is the ONLY writer of which one
   is current. The old screen kept a second copy of "am I on the queue / the map / a plan" in
   refs, so a tab click could change the address while the queue stayed on top of it, and
   re-tapping the open tab assigned a ref its own value and fired no watcher at all. Reading
   the whole view out of `useRoute()` removes the second copy rather than synchronising it. */
/* Statically imported: the page template links exactly one stylesheet, so a lazily loaded view
   would have to inject its own at runtime for the sake of a few kilobytes. */
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
