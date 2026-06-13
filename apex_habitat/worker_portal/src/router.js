import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "profile", component: () => import("./pages/Profile.vue") },
  { path: "/accommodation", name: "accommodation", component: () => import("./pages/Accommodation.vue") },
  { path: "/transport", name: "transport", component: () => import("./pages/Transport.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
  // Unknown hash → land on the Profile tab rather than a blank <router-view>.
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  // Each tab is a top-level screen; start it at the top on navigation, and
  // restore the prior position on browser Back/Forward.
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
