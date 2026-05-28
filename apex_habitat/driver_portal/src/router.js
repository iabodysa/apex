import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./pages/Home.vue") },
  { path: "/attendance", name: "attendance", component: () => import("./pages/Attendance.vue") },
  { path: "/trips", name: "trips", component: () => import("./pages/Trips.vue") },
  { path: "/fuel", name: "fuel", component: () => import("./pages/Fuel.vue") },
  { path: "/tickets", name: "tickets", component: () => import("./pages/Tickets.vue") },
];

export default createRouter({ history: createWebHashHistory(), routes });
