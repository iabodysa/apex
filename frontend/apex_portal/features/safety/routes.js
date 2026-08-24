import { __ } from "../../core/i18n.js";

export const safetyRoutes = Object.freeze([
  {
    path: "/rounds", name: "safety-rounds", feature: "safety",
    capability: "safety_read",
    component: () => import("./pages/SafetyRoundsPage.vue"),
    meta: { navigation: true, label: __("Safety Rounds"), capability: "safety_read", group: __("Maintenance & Safety") },
  },
  {
    path: "/rounds/:name", name: "safety-round-review", feature: "safety",
    capability: "safety_read",
    component: () => import("./pages/SafetyRoundReviewPage.vue"),
    meta: { navigation: false, label: __("Safety Round Review"), capability: "safety_read", group: __("Maintenance & Safety") },
  },
]);
