import "./styles.css";

const pages = Object.freeze({
    home: () => import("./pages/RepresentativeHomePage.vue"),
    vehicle: () => import("./pages/CurrentVehiclePage.vue"),
    receipt: () => import("./pages/VehicleReceiptPage.vue"),
    vehicleReturn: () => import("./pages/VehicleReturnPage.vue"),
    quota: () => import("./pages/FuelQuotaPage.vue"),
    fuel: () => import("./pages/FuelRequestPage.vue"),
    additionalFuel: () => import("./pages/AdditionalFuelRequestPage.vue"),
    incidents: () => import("./pages/RepresentativeIncidentsPage.vue"),
    incident: () => import("./pages/IncidentReportPage.vue"),
    complaints: () => import("./pages/RepresentativeComplaintsPage.vue"),
    complaintCreate: () => import("./pages/ComplaintCreatePage.vue"),
    complaint: () => import("./pages/ComplaintDetailPage.vue"),
});

const route = (path, name, label, icon, component, capability = "fleet.self.read") =>
    Object.freeze({
        path,
        name,
        component,
        feature: "fleet-self-service",
        capability,
        meta: Object.freeze({
            navigation: ["/", "/vehicle", "/fuel", "/incidents", "/complaints"].includes(path),
            label,
            icon,
        }),
    });

export function createFleetSelfRoutes() {
    return Object.freeze([
        route("/", "representative-home", "الرئيسية", "lucide-home", pages.home),
        route("/vehicle", "current-vehicle", "المركبة", "lucide-truck", pages.vehicle),
        route(
            "/vehicle/receipt",
            "vehicle-receipt",
            "استلام المركبة",
            "lucide-clipboard-check",
            pages.receipt,
            "fleet.self.handover",
        ),
        route(
            "/vehicle/return",
            "vehicle-return",
            "إرجاع المركبة",
            "lucide-undo-2",
            pages.vehicleReturn,
            "fleet.self.handover",
        ),
        route("/fuel", "fuel-quota", "الوقود", "lucide-fuel", pages.quota, "fleet.self.fuel"),
        route(
            "/fuel/request",
            "fuel-request",
            "طلب وقود",
            "lucide-plus",
            pages.fuel,
            "fleet.self.fuel",
        ),
        route(
            "/fuel/additional",
            "additional-fuel",
            "زيادة الوقود",
            "lucide-gauge",
            pages.additionalFuel,
            "fleet.self.fuel",
        ),
        route(
            "/incidents",
            "representative-incidents",
            "الحوادث",
            "lucide-triangle-alert",
            pages.incidents,
            "fleet.self.incident",
        ),
        route(
            "/incidents/new",
            "incident-report",
            "بلاغ حادث",
            "lucide-file-warning",
            pages.incident,
            "fleet.self.incident",
        ),
        route(
            "/complaints",
            "representative-complaints",
            "البلاغات",
            "lucide-messages-square",
            pages.complaints,
            "fleet.self.complaint",
        ),
        route(
            "/complaints/new",
            "complaint-create",
            "بلاغ جديد",
            "lucide-message-square-plus",
            pages.complaintCreate,
            "fleet.self.complaint",
        ),
        route(
            "/complaints/:name",
            "complaint-detail",
            "تفاصيل البلاغ",
            "lucide-message-square",
            pages.complaint,
            "fleet.self.complaint",
        ),
    ]);
}
