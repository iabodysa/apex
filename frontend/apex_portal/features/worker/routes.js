import WorkerPage from "./WorkerPage.vue";
import WorkerRequestForm from "./WorkerRequestForm.vue";
import WorkerTransportPage from "./WorkerTransportPage.vue";
import "./masar.css";

const page = (path, name, capability, label, icon, gateway, view = {}) => ({
  path, name, feature: "worker", capability, component: WorkerPage,
  meta: { navigation: !path.includes(":"), label, icon, view: { title: label, icon, gateway, ...view } },
});

export const workerRoutes = Object.freeze([
  page("/home", "worker-home", "worker.home", "اليوم", "home", "home", { eyebrow: "مسار", fields: [{ key: "profile.employee_name", label: "العامل" }, { key: "next_ride.route_name", label: "الرحلة القادمة" }] }),
  { path: "/transport", name: "worker-transport", feature: "worker", capability: "worker.trip.read", component: WorkerTransportPage, meta: { navigation: true, label: "التنقل", icon: "navigation" } },
  page("/requests", "worker-requests", "worker.request.read", "طلباتي", "inbox", "requests", { collections: ["requests"], detail: "/requests/:name", empty: "لم تقدم أي طلب بعد." }),
  page("/profile", "worker-profile", "worker.profile.read", "بياناتي", "user", "profile", { fields: [{ key: "employee_name", label: "الاسم" }, { key: "department", label: "القسم" }] }),
  page("/accommodation", "worker-accommodation", "worker.accommodation.read", "السكن", "map-pin", "accommodation", { fields: [{ key: "building.building_name", label: "المبنى" }, { key: "room.room_number", label: "الغرفة" }, { key: "bed.bed_code", label: "السرير" }] }),
  page("/custody", "worker-custody", "worker.custody.read", "العهد", "briefcase", "custody", { collections: ["items"], empty: "لا توجد عهد مسجلة عليك." }),
  { path: "/request-transport", name: "worker-request-transport", feature: "worker", capability: "worker.request.create", component: WorkerRequestForm, props: { transport: true }, meta: { navigation: false, label: "طلب نقل", icon: "plus" } },
  page("/requests/:name", "worker-request-detail", "worker.request.read", "تفاصيل الطلب", "file-text", "request", { fields: [{ key: "subject", label: "الموضوع" }, { key: "status", label: "الحالة" }, { key: "downstream_target", label: "المستند المرتبط" }] }),
]);
