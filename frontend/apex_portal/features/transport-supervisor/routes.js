import SupervisorPage from "./SupervisorPage.vue";
import RoutePlanForm from "./RoutePlanForm.vue";
import TransportMapPage from "./TransportMapPage.vue";
import "../worker/masar.css";

const page = (path, name, capability, label, icon, gateway, view = {}) => ({
  path, name, feature: "transport-supervisor", capability, component: SupervisorPage,
  meta: { navigation: !path.includes(":"), label, icon, view: { title: label, icon, gateway, ...view } },
});

export const supervisorRoutes = Object.freeze([
  page("/requests", "transport-requests", "transport.request.read", "طلبات النقل", "inbox", "requests", { collections: ["requests"] }),
  page("/shifts", "transport-shifts", "transport.shift.read", "الشفتات", "calendar", "shifts", { collections: ["items"] }),
  page("/plans", "transport-plans", "transport.plan.read", "خطط المسار", "map", "plans", { collections: ["plans"] }),
  { path: "/plans/new", name: "transport-plan-new", feature: "transport-supervisor", capability: "transport.plan.create", component: RoutePlanForm, meta: { navigation: false, label: "خطة جديدة", icon: "plus" } },
  page("/plans/:name", "transport-plan-detail", "transport.plan.read", "تفاصيل الخطة", "map-pin", "plan", { fields: [{ key: "route_name", label: "المسار" }, { key: "shift", label: "الشفت" }, { key: "driver", label: "السائق" }] }),
  page("/trips", "dispatch-trips", "transport.trip.read", "الرحلات", "navigation", "trips", { collections: ["trips"] }),
  page("/trips/:name", "dispatch-trip-control", "transport.trip.dispatch", "تشغيل الرحلة", "play-circle", "trip", { fields: [{ key: "status", label: "الحالة" }, { key: "vehicle", label: "المركبة" }, { key: "driver", label: "السائق" }] }),
  { path: "/map", name: "live-trips-map", feature: "transport-supervisor", capability: "transport.trip.location.read", component: TransportMapPage, meta: { navigation: true, label: "الخريطة", icon: "map-pin" } },
  page("/history", "movement-history", "transport.history.read", "سجل الحركة", "clock", "history", { collections: ["items"] }),
]);

export const supervisorRedirects = Object.freeze([
  { path: "/approvals", redirect: "/requests" },
  { path: "/routes", redirect: "/plans" },
  { path: "/plan/:name/:tab?", redirect: ({ params }) => `/plans/${params.name}` },
]);
