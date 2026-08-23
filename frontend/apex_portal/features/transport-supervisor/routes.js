import SupervisorPage from "./SupervisorPage.vue";
import TransportMapPage from "./TransportMapPage.vue";
import "./styles.css";

const pages = Object.freeze({
  requests: () => import("./pages/TransportRequestsPage.vue"),
  assignments: () => import("./pages/RouteAssignmentsPage.vue"),
  trips: () => import("./pages/DispatchTripsPage.vue"),
  history: () => import("./pages/MovementHistoryPage.vue"),
});

function navigationGroup(path) {
  if (path.startsWith("/requests")) return "الطلبات";
  if (path.startsWith("/assignments")) return "التخطيط";
  if (path.startsWith("/trips") || path === "/map") return "التشغيل المباشر";
  if (path.startsWith("/history")) return "السجل";
  return "تشغيل النقل";
}

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
    group: navigationGroup(path),
    view: { title: label, icon, ...view },
  },
});

export const supervisorRoutes = Object.freeze([
  page("/requests", "transport-requests", "transport.request.read", "طلبات النقل", "lucide-inbox", pages.requests, {
    doctype: "Transport Request",
    titleFields: ["from_location", "to_location", "requester_name"],
    fallbackTitle: "طلب نقل",
  }),
  page("/requests/:name", "transport-request-detail", "transport.request.read", "تفاصيل طلب النقل", "lucide-file-text", SupervisorPage, {
    doctype: "Transport Request",
    fields: [
      { key: "requester_name", label: "مقدم الطلب" },
      { key: "requested_by", label: "حساب مقدم الطلب", link: { doctype: "User", fieldname: "full_name", fallback: "مستخدم" } },
      { key: "service_line", label: "نوع النقل" },
      { key: "project", label: "المشروع", link: { doctype: "Project", fieldname: "project_name", fallback: "مشروع" } },
      { key: "accommodation_building", label: "مبنى الانطلاق", labelKey: "accommodation_building_label", link: { doctype: "Building", fieldname: "building_name", fallback: "مبنى سكن" } },
      { key: "from_location", label: "الانطلاق" },
      { key: "to_location", label: "الوجهة" },
      { key: "pickup_datetime", label: "موعد الانطلاق" },
      { key: "worker_count", label: "عدد الركاب" },
      { key: "assigned_to_trip", label: "الرحلة المسندة", link: { doctype: "Dispatch Trip", fieldname: "trip_title", fallback: "رحلة تشغيل" } },
    ],
  }),
  page("/assignments", "route-assignments", "transport.assignment.read", "التشغيل المتكرر", "lucide-repeat", pages.assignments, {
    doctype: "Route Assignment",
    titleFields: ["assignment_name", "shift_name"],
    fallbackTitle: "تشغيل متكرر",
    detail: "/assignments/:name",
  }),
  page("/assignments/:name", "route-assignment-detail", "transport.assignment.read", "تفاصيل التشغيل المتكرر", "lucide-repeat", SupervisorPage, {
    doctype: "Route Assignment",
    fields: [
      { key: "assignment_name", label: "التشغيل" },
      { key: "work_shift", label: "الشفت", link: { doctype: "Work Shift", fieldname: "shift_name", fallback: "وردية" } },
      { key: "route_template", label: "المسار", link: { doctype: "Route Template", fieldname: "template_name", fallback: "مسار" } },
      { key: "project", label: "المشروع", link: { doctype: "Project", fieldname: "project_name", fallback: "مشروع" } },
      { key: "driver", label: "السائق الافتراضي", link: { doctype: "Salis Driver", fieldname: "full_name", fallback: "سائق" } },
      { key: "vehicle", label: "المركبة الافتراضية", link: { doctype: "Salis Vehicle", fieldname: "plate_number", fallback: "مركبة" } },
      { key: "starts_on", label: "يبدأ في" },
      { key: "ends_on", label: "ينتهي في" },
      { key: "generated_through", label: "وُلّدت الرحلات حتى" },
    ],
  }),
  page("/trips", "dispatch-trips", "transport.trip.read", "الرحلات", "lucide-navigation", pages.trips, {
    doctype: "Dispatch Trip",
    titleFields: ["trip_title", "shift_name"],
    fallbackTitle: "رحلة تشغيل",
    detail: "/trips/:name",
  }),
  page("/trips/:name", "dispatch-trip-control", "transport.trip.read", "تشغيل الرحلة", "lucide-play-circle", SupervisorPage, {
    doctype: "Dispatch Trip",
    fields: [
      { key: "status", label: "الحالة" },
      { key: "trip_date", label: "التاريخ" },
      { key: "route_assignment", label: "التشغيل المتكرر", link: { doctype: "Route Assignment", fieldname: "assignment_name", fallback: "تشغيل متكرر" } },
      { key: "route_template", label: "المسار", link: { doctype: "Route Template", fieldname: "template_name", fallback: "مسار" } },
      { key: "project", label: "المشروع", link: { doctype: "Project", fieldname: "project_name", fallback: "مشروع" } },
      { key: "vehicle", label: "المركبة", link: { doctype: "Salis Vehicle", fieldname: "plate_number", fallback: "مركبة" } },
      { key: "driver", label: "السائق", link: { doctype: "Salis Driver", fieldname: "full_name", fallback: "سائق" } },
    ],
  }),
  {
    path: "/map",
    name: "live-trips-map",
    feature: "transport-supervisor",
    capability: "transport.trip.location.read",
    component: TransportMapPage,
    meta: { navigation: true, label: "الخريطة", icon: "lucide-map-pin", group: navigationGroup("/map") },
  },
  page("/history", "movement-history", "transport.history.read", "سجل الحركة", "lucide-clock", pages.history, {
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
