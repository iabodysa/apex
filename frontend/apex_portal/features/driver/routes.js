import DriverPage from "./DriverPage.vue";
import DriverTripPage from "./DriverTripPage.vue";
import DriverWelcomePage from "./DriverWelcomePage.vue";
import { __ } from "../../core/i18n.js";
import "../worker/masar.css";

const page = (path, name, capability, label, icon, endpoint, view = {}) => ({
  path,
  name,
  feature: "driver",
  capability,
  component: DriverPage,
  meta: {
    navigation: !path.includes(":"),
    label,
    icon,
    view: { title: label, icon, endpoint, ...view },
  },
});

export const driverRoutes = Object.freeze([
  {
    path: "/welcome",
    name: "driver-welcome",
    feature: "driver",
    capability: "driver.today",
    component: DriverWelcomePage,
    meta: { navigation: false, label: __("Welcome"), icon: "lucide-sparkles" },
  },
  page("/today", "driver-today", "driver.today", __("Day"), "lucide-home", "apex.salis.api.driver_portal.personal.get_masar_today", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: __("Today's trip"), detail: "/route/:trip", empty: __("There is no trip scheduled for you right now.") }),
  page("/route", "driver-route", "driver.trip.execute", __("Itinerary"), "lucide-navigation", "apex.salis.api.driver_portal.my_worker_route_today", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: __("trip"), detail: "/route/:trip", empty: __("No itinerary is assigned.") }),
  page("/trips", "driver-history", "driver.trip.read", __("History"), "lucide-clock", "apex.salis.api.driver_portal.my_trips_recent", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: __("Past trip"), detail: "/route/:trip" }),
  page("/requests", "driver-requests", "driver.employee.request.read", __("My Requests"), "lucide-inbox", "apex.salis.api.driver_portal.personal.get_my_resident_requests", { collections: ["requests"], titleFields: ["request_category", "description"], fallbackTitle: __("Housing Request") }),
  page("/profile", "driver-profile", "driver.profile.read", __("My Profile"), "lucide-user", "apex.salis.api.driver_portal.get_driver_profile", {
    fields: [
      { key: "full_name", label: __("Name") },
      { key: "phone", label: __("Mobile") },
    ],
  }),
  page("/accommodation", "driver-accommodation", "driver.employee.accommodation.read", __("Accommodation"), "lucide-map-pin", "apex.salis.api.driver_portal.personal.get_my_accommodation", {
    fields: [
      { key: "building", label: __("Building") },
      { key: "room", label: __("Room") },
    ],
  }),
  page("/custody", "driver-custody", "driver.employee.custody.read", __("My Custody"), "lucide-briefcase", "apex.salis.api.driver_portal.personal.get_my_custody", { collections: ["items"], titleFields: ["item_name", "item"], fallbackTitle: __("Custody item") }),
  {
    path: "/route/:trip",
    name: "driver-trip",
    feature: "driver",
    capability: "driver.trip.execute",
    component: DriverTripPage,
    meta: { navigation: false, label: __("Trip Execution"), icon: "lucide-map" },
  },
]);
