import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./pages/Home.vue") },
  { path: "/profile", name: "profile", component: () => import("./pages/Profile.vue") },
  { path: "/accommodation", name: "accommodation", component: () => import("./pages/Accommodation.vue") },
  { path: "/transport", name: "transport", component: () => import("./pages/Transport.vue") },
  { path: "/custody", name: "custody", component: () => import("./pages/Custody.vue") },
  { path: "/requests", name: "requests", component: () => import("./pages/Requests.vue") },
  { path: "/requests/:name", name: "request-detail", component: () => import("./pages/RequestDetail.vue") },
  // [#a7w9tx]
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  // [#dy6jiy]
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 };
  },
});
