import DriverPage from "./DriverPage.vue";
import "../worker/masar.css";

const page = (path, name, capability, label, icon, gateway, view = {}) => ({
  path, name, feature: "driver", capability, component: DriverPage,
  meta: { navigation: !path.includes(":"), label, icon, view: { title: label, icon, gateway, ...view } },
});

export const driverRoutes = Object.freeze([
  page("/today", "driver-today", "driver.today", "اليوم", "home", "today", { collections: ["trips"], empty: "لا توجد رحلة مسندة اليوم." }),
  page("/profile", "driver-profile", "driver.profile.read", "بياناتي", "user", "profile", { fields: [{ key: "full_name", label: "الاسم" }, { key: "phone", label: "الجوال" }] }),
  page("/accommodation", "driver-accommodation", "driver.employee.accommodation.read", "السكن", "map-pin", "accommodation", { fields: [{ key: "building", label: "المبنى" }, { key: "room", label: "الغرفة" }] }),
  page("/custody", "driver-custody", "driver.employee.custody.read", "العهد", "briefcase", "custody", { collections: ["items"] }),
  page("/requests", "driver-requests", "driver.employee.request.read", "طلباتي", "inbox", "requests", { collections: ["requests"] }),
  page("/route", "driver-route", "driver.trip.execute", "خط السير", "navigation", "route", { collections: ["trips"], empty: "لا يوجد خط سير مسند." }),
  page("/route/:trip", "driver-trip", "driver.trip.execute", "تنفيذ الرحلة", "map", "trip", { collections: ["stops"], execution: true }),
  page("/trips", "driver-history", "driver.trip.read", "السجل", "clock", "trips", { collections: ["trips"] }),
]);
