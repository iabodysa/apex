import WorkerPage from "./WorkerPage.vue";
import WorkerRequestForm from "./WorkerRequestForm.vue";
import WorkerTransportPage from "./WorkerTransportPage.vue";
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
  page("/home", "worker-home", "worker.home", "اليوم", "lucide-home", "apex.salis.api.masar.get_worker_home", {
    eyebrow: "مسار",
    fields: [
      { key: "profile.employee_name", label: "العامل" },
      { key: "next_ride.route_name", label: "الرحلة القادمة" },
    ],
  }),
  {
    path: "/transport",
    name: "worker-transport",
    feature: "worker",
    capability: "worker.trip.read",
    component: WorkerTransportPage,
    meta: { navigation: true, label: "التنقل", icon: "lucide-navigation" },
  },
  page("/requests", "worker-requests", "worker.request.read", "طلباتي", "lucide-inbox", "apex.salis.api.masar.list_worker_requests", { collections: ["requests"], titleFields: ["request_category", "description"], fallbackTitle: "طلب سكن", detail: "/requests/:name", empty: "لم تقدم أي طلب بعد." }),
  page("/profile", "worker-profile", "worker.profile.read", "بياناتي", "lucide-user", "apex.salis.api.masar.get_worker_context", {
    fields: [
      { key: "employee_name", label: "الاسم" },
      { key: "department", label: "القسم" },
    ],
  }),
  page("/accommodation", "worker-accommodation", "worker.accommodation.read", "السكن", "lucide-map-pin", "apex.salis.api.masar.get_worker_accommodation", {
    fields: [
      { key: "building.building_name", label: "المبنى" },
      { key: "room.room_number", label: "الغرفة" },
      { key: "bed.bed_code", label: "السرير" },
    ],
  }),
  page("/custody", "worker-custody", "worker.custody.read", "العهد", "lucide-briefcase", "apex.salis.api.masar.get_worker_custody", { collections: ["items"], titleFields: ["item_name", "item"], fallbackTitle: "صنف عهدة", empty: "لا توجد عهد مسجلة عليك." }),
  {
    path: "/request-transport",
    name: "worker-request-transport",
    feature: "worker",
    capability: "worker.request.create",
    component: WorkerRequestForm,
    props: { transport: true },
    meta: { navigation: false, label: "طلب نقل", icon: "lucide-plus" },
  },
  page("/requests/:name", "worker-request-detail", "worker.request.read", "تفاصيل الطلب", "lucide-file-text", "apex.salis.api.masar.get_worker_request_detail", {
    fields: [
      { key: "subject", label: "الموضوع" },
      { key: "status", label: "الحالة" },
      { key: "downstream_target", label: "المستند المرتبط" },
    ],
  }),
]);
