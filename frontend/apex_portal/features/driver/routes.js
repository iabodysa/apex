import DriverPage from "./DriverPage.vue";
import DriverTripPage from "./DriverTripPage.vue";
import "../worker/masar.css";

const page = (path, name, capability, label, icon, gateway, view = {}) => ({
  path, name, feature: "driver", capability, component: DriverPage,
  meta: { navigation: !path.includes(":"), label, icon, view: { title: label, icon, gateway, ...view } },
});

export const driverRoutes = Object.freeze([
  page("/today", "driver-today", "driver.today", "اليوم", "home", "today", { collections: ["trips"], detail: "/route/:trip", empty: "لا توجد رحلة مسندة اليوم." }),
  page("/route", "driver-route", "driver.trip.execute", "خط السير", "navigation", "route", { collections: ["trips"], detail: "/route/:trip", empty: "لا يوجد خط سير مسند." }),
  page("/trips", "driver-history", "driver.trip.read", "السجل", "clock", "trips", { collections: ["trips"], detail: "/route/:trip" }),
  page("/requests", "driver-requests", "driver.employee.request.read", "طلباتي", "inbox", "requests", { collections: ["requests"] }),
  page("/profile", "driver-profile", "driver.profile.read", "بياناتي", "user", "profile", { fields: [{ key: "full_name", label: "الاسم" }, { key: "phone", label: "الجوال" }] }),
  page("/accommodation", "driver-accommodation", "driver.employee.accommodation.read", "السكن", "map-pin", "accommodation", { fields: [{ key: "building", label: "المبنى" }, { key: "room", label: "الغرفة" }] }),
  page("/custody", "driver-custody", "driver.employee.custody.read", "العهد", "briefcase", "custody", { collections: ["items"] }),
  { path: "/route/:trip", name: "driver-trip", feature: "driver", capability: "driver.trip.execute", component: DriverTripPage, meta: { navigation: false, label: "تنفيذ الرحلة", icon: "map" } },
]);
