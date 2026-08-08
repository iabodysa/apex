// Copyright (c) 2026, afmcoltd
import { createRouter, createWebHashHistory } from "vue-router";

import BoardView from "./views/BoardView.vue";

/* One screen, and the whole of its state travels in the query string: filters, search, status
   pill, triage chip, sort, view, the open vehicle and the alerts drawer. The board had no URL
   state at all, so a refresh, a Back press or a link to a colleague lost every one of them. */
const routes = [
  { path: "/", name: "board", component: BoardView },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    /* Only a real navigation resets the scroll; changing a filter keeps the reader's place. */
    if (to.path !== from.path) return savedPosition || { top: 0 };
    return false;
  },
});
