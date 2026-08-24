import SupervisorPage from "./SupervisorPage.vue";
import TransportMapPage from "./TransportMapPage.vue";
import "./styles.css";
import { __ } from "../../core/i18n.js";

const pages = Object.freeze({
  requests: () => import("./pages/TransportRequestsPage.vue"),
  assignments: () => import("./pages/RouteAssignmentsPage.vue"),
  trips: () => import("./pages/DispatchTripsPage.vue"),
  history: () => import("./pages/MovementHistoryPage.vue"),
});

function navigationGroup(path) {
  if (path.startsWith("/requests")) return __("Requests");
  if (path.startsWith("/assignments")) return __("Planning");
  if (path.startsWith("/trips") || path === "/map") return __("Live Operations");
  if (path.startsWith("/history")) return __("History");
  return __("Transport Operations");
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
  page("/requests", "transport-requests", "transport.request.read", __("Transport Requests"), "lucide-inbox", pages.requests, {
    doctype: "Transport Request",
    titleFields: ["from_location", "to_location", "requester_name"],
    fallbackTitle: __("Transport Request"),
  }),
  page("/requests/:name", "transport-request-detail", "transport.request.read", __("Transport Request Details"), "lucide-file-text", SupervisorPage, {
    doctype: "Transport Request",
    fields: [
      { key: "requester_name", label: __("Request Submitter") },
      { key: "requested_by", label: __("Requester Account"), link: { doctype: "User", fieldname: "full_name", fallback: __("user") } },
      { key: "service_line", label: __("Transport Type") },
      { key: "project", label: __("Project"), link: { doctype: "Project", fieldname: "project_name", fallback: __("project") } },
      { key: "accommodation_building", label: __("Origin Building"), labelKey: "accommodation_building_label", link: { doctype: "Building", fieldname: "building_name", fallback: __("Housing Building") } },
      { key: "from_location", label: __("Departure") },
      { key: "to_location", label: __("Destination") },
      { key: "pickup_datetime", label: __("Departure Time") },
      { key: "worker_count", label: __("Passenger Count") },
      { key: "assigned_to_trip", label: __("Linked Trip"), link: { doctype: "Dispatch Trip", fieldname: "trip_title", fallback: __("Operational Trip") } },
    ],
  }),
  page("/assignments", "route-assignments", "transport.assignment.read", __("Recurring Operations"), "lucide-repeat", pages.assignments, {
    doctype: "Route Assignment",
    titleFields: ["assignment_name", "shift_name"],
    fallbackTitle: __("recurring operation"),
    detail: "/assignments/:name",
  }),
  page("/assignments/:name", "route-assignment-detail", "transport.assignment.read", __("Recurring Operation Details"), "lucide-repeat", SupervisorPage, {
    doctype: "Route Assignment",
    fields: [
      { key: "assignment_name", label: __("Operation") },
      { key: "work_shift", label: __("Duty Shift"), link: { doctype: "Work Shift", fieldname: "shift_name", fallback: __("shift") } },
      { key: "route_template", label: __("Route"), link: { doctype: "Route Template", fieldname: "template_name", fallback: __("Masar") } },
      { key: "project", label: __("Project"), link: { doctype: "Project", fieldname: "project_name", fallback: __("project") } },
      { key: "driver", label: __("Default Driver"), link: { doctype: "Salis Driver", fieldname: "full_name", fallback: __("Driver") } },
      { key: "vehicle", label: __("Default Vehicle"), link: { doctype: "Salis Vehicle", fieldname: "plate_number", fallback: __("Vehicle") } },
      { key: "starts_on", label: __("Starts On") },
      { key: "ends_on", label: __("ends on") },
      { key: "generated_through", label: __("Trips Generated Through") },
    ],
  }),
  page("/trips", "dispatch-trips", "transport.trip.read", __("Trips"), "lucide-navigation", pages.trips, {
    doctype: "Dispatch Trip",
    titleFields: ["trip_title", "shift_name"],
    fallbackTitle: __("Operational Trip"),
    detail: "/trips/:name",
  }),
  page("/trips/:name", "dispatch-trip-control", "transport.trip.read", __("Trip Operation"), "lucide-play-circle", SupervisorPage, {
    doctype: "Dispatch Trip",
    fields: [
      { key: "status", label: __("Status") },
      { key: "trip_date", label: __("Date") },
      { key: "route_assignment", label: __("Recurring Operations"), link: { doctype: "Route Assignment", fieldname: "assignment_name", fallback: __("recurring operation") } },
      { key: "route_template", label: __("Route"), link: { doctype: "Route Template", fieldname: "template_name", fallback: __("Masar") } },
      { key: "project", label: __("Project"), link: { doctype: "Project", fieldname: "project_name", fallback: __("project") } },
      { key: "vehicle", label: __("vehicle"), link: { doctype: "Salis Vehicle", fieldname: "plate_number", fallback: __("Vehicle") } },
      { key: "driver", label: __("driver"), link: { doctype: "Salis Driver", fieldname: "full_name", fallback: __("Driver") } },
    ],
  }),
  {
    path: "/map",
    name: "live-trips-map",
    feature: "transport-supervisor",
    capability: "transport.trip.location.read",
    component: TransportMapPage,
    meta: { navigation: true, label: __("Map"), icon: "lucide-map-pin", group: navigationGroup("/map") },
  },
  page("/history", "movement-history", "transport.history.read", __("Movement History"), "lucide-clock", pages.history, {
    doctype: "Dispatch Trip",
    titleFields: ["trip_title", "shift_name"],
    fallbackTitle: __("Past Movement"),
  }),
]);

export const supervisorRedirects = Object.freeze([
  { path: "/approvals", redirect: "/requests" },
  { path: "/routes", redirect: "/assignments" },
  { path: "/shifts", redirect: "/assignments" },
  { path: "/plans", redirect: "/assignments" },
  { path: "/plan/:name/:tab?", redirect: "/assignments" },
]);
