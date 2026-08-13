import SupervisorPage from "./SupervisorPage.vue";
import TransportMapPage from "./TransportMapPage.vue";
import "./styles.css";

const pages = Object.freeze({
  requests: () => import("./pages/TransportRequestsPage.vue"),
  assignments: () => import("./pages/RouteAssignmentsPage.vue"),
  trips: () => import("./pages/DispatchTripsPage.vue"),
  history: () => import("./pages/MovementHistoryPage.vue"),
});

const page = (path, name, capability, label, icon, component, view = {}) => ({
  path,
  name,
  feature: "transport-supervisor",
  capability,
  component,
  meta: {
    navigation: !path.includes(":"),
    label,
    icon,
    view: { title: label, icon, ...view },
  },
});

export const supervisorRoutes = Object.freeze([
  page("/requests", "transport-requests", "transport.request.read", "طلبات النقل", "inbox", pages.requests, {
    doctype: "Transport Request",
    titleFields: ["from_location", "to_location", "requester_name"],
    fallbackTitle: "طلب نقل",
  }),
  page("/requests/:name", "transport-request-detail", "transport.request.read", "تفاصيل طلب النقل", "file-text", SupervisorPage, {
    doctype: "Transport Request",
    fields: [
      { key: "requester_name", label: "مقدم الطلب" },
      { key: "service_line", label: "نوع النقل" },
      { key: "project", label: "المشروع" },
      { key: "from_location", label: "الانطلاق" },
      { key: "to_location", label: "الوجهة" },
      { key: "pickup_datetime", label: "موعد الانطلاق" },
      { key: "worker_count", label: "عدد الركاب" },
      { key: "assigned_to_trip", label: "الرحلة المسندة" },
    ],
  }),
  page("/assignments", "route-assignments", "transport.assignment.read", "التشغيل المتكرر", "repeat", pages.assignments, {
    doctype: "Route Assignment",
    titleFields: ["assignment_name", "shift_name"],
    fallbackTitle: "تشغيل متكرر",
    detail: "/assignments/:name",
  }),
  page("/assignments/:name", "route-assignment-detail", "transport.assignment.read", "تفاصيل التشغيل المتكرر", "repeat", SupervisorPage, {
    doctype: "Route Assignment",
    fields: [
      { key: "assignment_name", label: "التشغيل" },
      { key: "work_shift", label: "الشفت" },
      { key: "route_template", label: "المسار" },
      { key: "project", label: "المشروع" },
      { key: "driver", label: "السائق الافتراضي" },
      { key: "vehicle", label: "المركبة الافتراضية" },
      { key: "starts_on", label: "يبدأ في" },
      { key: "ends_on", label: "ينتهي في" },
      { key: "generated_through", label: "وُلّدت الرحلات حتى" },
    ],
  }),
  page("/trips", "dispatch-trips", "transport.trip.read", "الرحلات", "navigation", pages.trips, {
    doctype: "Dispatch Trip",
    titleFields: ["trip_title", "shift_name"],
    fallbackTitle: "رحلة تشغيل",
    detail: "/trips/:name",
  }),
  page("/trips/:name", "dispatch-trip-control", "transport.trip.read", "تشغيل الرحلة", "play-circle", SupervisorPage, {
    doctype: "Dispatch Trip",
    fields: [
      { key: "status", label: "الحالة" },
      { key: "trip_date", label: "التاريخ" },
      { key: "route_assignment", label: "التشغيل المتكرر" },
      { key: "route_template", label: "المسار" },
      { key: "project", label: "المشروع" },
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
  page("/history", "movement-history", "transport.history.read", "سجل الحركة", "clock", pages.history, {
    doctype: "Dispatch Trip",
    titleFields: ["trip_title", "shift_name"],
    fallbackTitle: "حركة سابقة",
  }),
]);

export const supervisorRedirects = Object.freeze([
  { path: "/approvals", redirect: "/requests" },
  { path: "/routes", redirect: "/assignments" },
  { path: "/shifts", redirect: "/assignments" },
  { path: "/plans", redirect: "/assignments" },
  { path: "/plan/:name/:tab?", redirect: "/assignments" },
]);
