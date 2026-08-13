import DriverPage from "./DriverPage.vue";
import DriverTripPage from "./DriverTripPage.vue";
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
  page("/today", "driver-today", "driver.today", "اليوم", "home", "apex.salis.api.driver_portal.personal.get_masar_today", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: "رحلة اليوم", detail: "/route/:trip", empty: "لا توجد رحلة مسندة اليوم." }),
  page("/route", "driver-route", "driver.trip.execute", "خط السير", "navigation", "apex.salis.api.driver_portal.my_worker_route_today", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: "رحلة", detail: "/route/:trip", empty: "لا يوجد خط سير مسند." }),
  page("/trips", "driver-history", "driver.trip.read", "السجل", "clock", "apex.salis.api.driver_portal.my_trips_recent", { collections: ["trips"], titleFields: ["route_name", "shift_name", "route_plan"], fallbackTitle: "رحلة سابقة", detail: "/route/:trip" }),
  page("/requests", "driver-requests", "driver.employee.request.read", "طلباتي", "inbox", "apex.salis.api.driver_portal.personal.get_my_resident_requests", { collections: ["requests"], titleFields: ["request_category", "description"], fallbackTitle: "طلب سكن" }),
  page("/profile", "driver-profile", "driver.profile.read", "بياناتي", "user", "apex.salis.api.driver_portal.get_driver_profile", {
    fields: [
      { key: "full_name", label: "الاسم" },
      { key: "phone", label: "الجوال" },
    ],
  }),
  page("/accommodation", "driver-accommodation", "driver.employee.accommodation.read", "السكن", "map-pin", "apex.salis.api.driver_portal.personal.get_my_accommodation", {
    fields: [
      { key: "building", label: "المبنى" },
      { key: "room", label: "الغرفة" },
    ],
  }),
  page("/custody", "driver-custody", "driver.employee.custody.read", "العهد", "briefcase", "apex.salis.api.driver_portal.personal.get_my_custody", { collections: ["items"], titleFields: ["item_name", "item"], fallbackTitle: "صنف عهدة" }),
  {
    path: "/route/:trip",
    name: "driver-trip",
    feature: "driver",
    capability: "driver.trip.execute",
    component: DriverTripPage,
    meta: { navigation: false, label: "تنفيذ الرحلة", icon: "map" },
  },
]);
