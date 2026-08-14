export const safetyRoutes = Object.freeze([
  {
    path: "/rounds", name: "safety-rounds", feature: "safety",
    capability: "safety_read",
    component: () => import("./pages/SafetyRoundsPage.vue"),
    meta: { navigation: true, label: "جولات السلامة", capability: "safety_read", group: "الصيانة والسلامة" },
  },
  {
    path: "/rounds/:name", name: "safety-round-review", feature: "safety",
    capability: "safety_read",
    component: () => import("./pages/SafetyRoundReviewPage.vue"),
    meta: { navigation: false, label: "مراجعة جولة السلامة", capability: "safety_read", group: "الصيانة والسلامة" },
  },
]);
