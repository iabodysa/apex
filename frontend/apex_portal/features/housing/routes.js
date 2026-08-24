import "./housing.css";
import { __ } from "../../core/i18n.js";

const pages = Object.freeze({
  today: () => import("./pages/TodayPage.vue"),
  count: () => import("./pages/InventoryCountPage.vue"),
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
    meta: { navigation: false, label: __("Overview"), capability: "estate_read", group: __("Day") },
  },
  route("/today", "housing-today", __("Today's Tasks"), "today", pages.today, __("Day")),
  route("/count", "housing-count", __("Inventory"), "count", pages.count, __("Custody & Inventory")),
  route("/beds", "housing-beds", __("Rooms & Beds"), "estate_read", pages.beds, __("Housing")),
  route("/beds/:bed", "housing-bed-detail", __("Bed Details"), "estate_read", pages.bedDetail),
  route("/arrivals", "housing-arrivals", __("Arrivals"), "check_in", pages.arrivals, __("Housing")),
  route("/transfer", "housing-transfer", __("Transfer Resident"), "transfer", pages.transfer, __("Housing")),
  route("/custody", "housing-custody", __("Custody Items"), "custody_read", pages.custody, __("Custody & Inventory")),
  route("/delivery", "housing-delivery", __("Asset Handover"), "delivery_read", pages.delivery, __("Custody & Inventory")),
  route("/delivery/:name", "housing-delivery-detail", __("Handover Details"), "delivery_read", pages.deliveryDetail),
  route("/maintenance", "housing-maintenance", __("Maintenance Requests"), "maintenance_read", pages.maintenance, __("Maintenance & Safety")),
  route("/maintenance/new", "housing-maintenance-new", __("New Maintenance Request"), "maintenance_create", pages.maintenanceNew, __("Maintenance & Safety")),
  route("/maintenance/:name", "housing-maintenance-detail", __("Maintenance Request Details"), "maintenance_read", pages.maintenanceDetail),
]);
