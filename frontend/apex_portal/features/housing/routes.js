import "./housing.css";

const pages = Object.freeze({
  today: () => import("./pages/TodayPage.vue"),
  count: () => import("./pages/InventoryCountPage.vue"),
  countItem: () => import("./pages/InventoryItemPage.vue"),
  beds: () => import("./pages/BedsPage.vue"),
  bedDetail: () => import("./pages/BedDetailPage.vue"),
  arrivals: () => import("./pages/ArrivalsPage.vue"),
  transfer: () => import("./pages/TransferPage.vue"),
  custody: () => import("./pages/CustodyPage.vue"),
  delivery: () => import("./pages/DeliveryListPage.vue"),
  deliveryDetail: () => import("./pages/DeliveryDetailPage.vue"),
  maintenance: () => import("./pages/MaintenanceRequestsPage.vue"),
  maintenanceNew: () => import("./pages/MaintenanceRequestCreatePage.vue"),
  maintenanceDetail: () => import("./pages/MaintenanceRequestDetailPage.vue"),
});

const route = (path, name, label, capability, component, group = "") => ({
  path,
  name,
  feature: "housing",
  capability,
  component,
  meta: {
    navigation: !path.includes(":") && !["/overview", "/maintenance/new"].includes(path),
    label,
    capability,
    group,
  },
});

export const housingRoutes = Object.freeze([
  {
    path: "/overview",
    name: "housing-overview",
    feature: "housing",
    capability: "estate_read",
    redirect: "/today",
    meta: { navigation: false, label: "نظرة عامة", capability: "estate_read", group: "اليوم" },
  },
  route("/today", "housing-today", "مهام اليوم", "today", pages.today, "اليوم"),
  route("/count", "housing-count", "الجرد", "count", pages.count, "العهد والجرد"),
  route("/count/:item", "housing-count-item", "تفاصيل الجرد", "count", pages.countItem),
  route("/beds", "housing-beds", "الغرف والأسرّة", "estate_read", pages.beds, "السكن"),
  route("/beds/:bed", "housing-bed-detail", "تفاصيل السرير", "estate_read", pages.bedDetail),
  route("/arrivals", "housing-arrivals", "القادمون", "check_in", pages.arrivals, "السكن"),
  route("/transfer", "housing-transfer", "نقل الساكن", "transfer", pages.transfer, "السكن"),
  route("/custody", "housing-custody", "العهد", "custody_read", pages.custody, "العهد والجرد"),
  route("/delivery", "housing-delivery", "تسليم الأصول", "delivery_read", pages.delivery, "العهد والجرد"),
  route("/delivery/:name", "housing-delivery-detail", "تفاصيل التسليم", "delivery_read", pages.deliveryDetail),
  route("/maintenance", "housing-maintenance", "طلبات الصيانة", "maintenance_read", pages.maintenance, "الصيانة والسلامة"),
  route("/maintenance/new", "housing-maintenance-new", "طلب صيانة جديد", "maintenance_create", pages.maintenanceNew, "الصيانة والسلامة"),
  route("/maintenance/:name", "housing-maintenance-detail", "تفاصيل طلب الصيانة", "maintenance_read", pages.maintenanceDetail),
]);
