import SupervisorPage from "./SupervisorPage.vue";
import RoutePlanForm from "./RoutePlanForm.vue";
import TransportMapPage from "./TransportMapPage.vue";

const page = (path, name, capability, label, icon, endpoint, view = {}) => ({
  path,
  name,
  feature: "transport-supervisor",
  capability,
  component: SupervisorPage,
  meta: {
    navigation: !path.includes(":"),
    label,
    icon,
    view: { title: label, icon, endpoint, ...view },
  },
});

export const supervisorRoutes = Object.freeze([
  page("/requests", "transport-requests", "transport.request.read", "طلبات النقل", "inbox", "apex.salis.api.route_supervisor.get_transport_requests", { collections: ["requests"], titleFields: ["requester_name", "service_line", "to_location", "from_location"], fallbackTitle: "طلب نقل" }),
  page("/shifts", "transport-shifts", "transport.shift.read", "الشفتات", "calendar", "apex.salis.api.route_supervisor.get_shift_routes", { collections: ["items"], titleFields: ["shift_name", "route_name"], fallbackTitle: "شفت تشغيل" }),
  page("/plans", "transport-plans", "transport.plan.read", "خطط المسار", "map", "apex.salis.api.route_supervisor.get_route_plans", { collections: ["plans"], titleFields: ["route_name"], fallbackTitle: "خطة مسار", detail: "/plans/:name" }),
  {
    path: "/plans/new",
    name: "transport-plan-new",
    feature: "transport-supervisor",
    capability: "transport.plan.create",
    component: RoutePlanForm,
    meta: { navigation: false, label: "خطة جديدة", icon: "plus" },
  },
  page("/plans/:name", "transport-plan-detail", "transport.plan.read", "تفاصيل الخطة", "map-pin", "apex.salis.api.route_supervisor.get_route_plan", {
    fields: [
      { key: "route_name", label: "المسار" },
      { key: "shift", label: "الشفت" },
      { key: "driver", label: "السائق" },
    ],
  }),
  page("/trips", "dispatch-trips", "transport.trip.read", "الرحلات", "navigation", "apex.salis.api.route_supervisor.get_dispatch_trips", { collections: ["trips"], titleFields: ["route_name", "shift_name"], fallbackTitle: "رحلة تشغيل", detail: "/trips/:name" }),
  page("/trips/:name", "dispatch-trip-control", "transport.trip.dispatch", "تشغيل الرحلة", "play-circle", "apex.salis.api.route_supervisor.get_dispatch_trip", {
    fields: [
      { key: "status", label: "الحالة" },
      { key: "vehicle", label: "المركبة" },
      { key: "driver", label: "السائق" },
    ],
  }),
  {
    path: "/map",
    name: "live-trips-map",
    feature: "transport-supervisor",
    capability: "transport.trip.location.read",
    component: TransportMapPage,
    meta: { navigation: true, label: "الخريطة", icon: "map-pin" },
  },
  page("/history", "movement-history", "transport.history.read", "سجل الحركة", "clock", "apex.salis.api.route_supervisor.get_movement_history", { collections: ["items"], titleFields: ["route_name", "shift_name"], fallbackTitle: "حركة سابقة" }),
]);

export const supervisorRedirects = Object.freeze([
  { path: "/approvals", redirect: "/requests" },
  { path: "/routes", redirect: "/plans" },
  { path: "/plan/:name/:tab?", redirect: ({ params }) => `/plans/${params.name}` },
]);
