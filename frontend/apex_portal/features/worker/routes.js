import WorkerPage from "./WorkerPage.vue";
import WorkerRequestForm from "./WorkerRequestForm.vue";
import WorkerTransportPage from "./WorkerTransportPage.vue";
import { __ } from "../../core/i18n.js";
import "./masar.css";

const page = (path, name, capability, label, icon, endpoint, view = {}) => ({
  path,
  name,
  feature: "worker",
  capability,
  component: WorkerPage,
  meta: {
    navigation: !path.includes(":"),
    label,
    icon,
    view: { title: label, icon, endpoint, ...view },
  },
});

export const workerRoutes = Object.freeze([
  page("/home", "worker-home", "worker.home", __("Day"), "lucide-home", "apex.salis.api.masar.get_worker_home", {
    eyebrow: __("Masar"),
    fields: [
      { key: "profile.employee_name", label: __("the worker") },
      { key: "next_ride.route_name", label: __("Next trip") },
    ],
  }),
  {
    path: "/transport",
    name: "worker-transport",
    feature: "worker",
    capability: "worker.trip.read",
    component: WorkerTransportPage,
    meta: { navigation: true, label: __("Mobility"), icon: "lucide-navigation" },
  },
  page("/requests", "worker-requests", "worker.request.read", __("My Requests"), "lucide-inbox", "apex.salis.api.masar.list_worker_requests", { collections: ["requests"], titleFields: ["request_category", "description"], fallbackTitle: __("Housing Request"), detail: "/requests/:name", empty: __("You have not submitted any request yet.") }),
  page("/profile", "worker-profile", "worker.profile.read", __("My Profile"), "lucide-user", "apex.salis.api.masar.get_worker_context", {
    fields: [
      { key: "employee_name", label: __("Name") },
      { key: "department", label: __("Department") },
    ],
  }),
  page("/accommodation", "worker-accommodation", "worker.accommodation.read", __("Accommodation"), "lucide-map-pin", "apex.salis.api.masar.get_worker_accommodation", {
    fields: [
      { key: "building.building_name", label: __("Building") },
      { key: "room.room_number", label: __("Room") },
      { key: "bed.bed_code", label: __("bed") },
    ],
  }),
  page("/custody", "worker-custody", "worker.custody.read", __("My Custody"), "lucide-briefcase", "apex.salis.api.masar.get_worker_custody", { collections: ["items"], titleFields: ["item_name", "item"], fallbackTitle: __("Custody item"), empty: __("You have no custody items registered.") }),
  {
    path: "/request-transport",
    name: "worker-request-transport",
    feature: "worker",
    capability: "worker.request.create",
    component: WorkerRequestForm,
    props: { transport: true },
    meta: { navigation: false, label: __("Transport Request"), icon: "lucide-plus" },
  },
  page("/requests/:name", "worker-request-detail", "worker.request.read", __("Request Details"), "lucide-file-text", "apex.salis.api.masar.get_worker_request_detail", {
    fields: [
      { key: "subject", label: __("Subject") },
      { key: "status", label: __("Status") },
      { key: "downstream_target", label: __("Linked document") },
    ],
  }),
]);
