// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

import BoardView from "./views/BoardView.vue";

const routes = [
  { path: "/", name: "board", component: BoardView },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (to.path !== from.path) return savedPosition || { top: 0 };
    return false;
  },
});
