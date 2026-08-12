import AdditionalFuelRequestPage from "./pages/AdditionalFuelRequestPage.vue";
import ComplaintCreatePage from "./pages/ComplaintCreatePage.vue";
import ComplaintDetailPage from "./pages/ComplaintDetailPage.vue";
import FuelQuotaPage from "./pages/FuelQuotaPage.vue";
import FuelRequestPage from "./pages/FuelRequestPage.vue";
import IncidentReportPage from "./pages/IncidentReportPage.vue";
import CurrentVehiclePage from "./pages/CurrentVehiclePage.vue";
import RepresentativeComplaintsPage from "./pages/RepresentativeComplaintsPage.vue";
import RepresentativeHomePage from "./pages/RepresentativeHomePage.vue";
import RepresentativeIncidentsPage from "./pages/RepresentativeIncidentsPage.vue";
import VehicleReceiptPage from "./pages/VehicleReceiptPage.vue";
import VehicleReturnPage from "./pages/VehicleReturnPage.vue";
import "./styles.css";

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
        route("/", "representative-home", "الرئيسية", "home", RepresentativeHomePage),
        route("/vehicle", "current-vehicle", "المركبة", "truck", CurrentVehiclePage),
        route(
            "/vehicle/receipt",
            "vehicle-receipt",
            "استلام المركبة",
            "clipboard-check",
            VehicleReceiptPage,
            "fleet.self.handover",
        ),
        route(
            "/vehicle/return",
            "vehicle-return",
            "إرجاع المركبة",
            "undo-2",
            VehicleReturnPage,
            "fleet.self.handover",
        ),
        route("/fuel", "fuel-quota", "الوقود", "fuel", FuelQuotaPage),
        route(
            "/fuel/request",
            "fuel-request",
            "طلب وقود",
            "plus",
            FuelRequestPage,
            "fleet.self.fuel",
        ),
        route(
            "/fuel/additional",
            "additional-fuel",
            "زيادة الوقود",
            "gauge",
            AdditionalFuelRequestPage,
            "fleet.self.fuel",
        ),
        route(
            "/incidents",
            "representative-incidents",
            "الحوادث",
            "triangle-alert",
            RepresentativeIncidentsPage,
        ),
        route(
            "/incidents/new",
            "incident-report",
            "بلاغ حادث",
            "file-warning",
            IncidentReportPage,
            "fleet.self.incident",
        ),
        route(
            "/complaints",
            "representative-complaints",
            "البلاغات",
            "messages-square",
            RepresentativeComplaintsPage,
        ),
        route(
            "/complaints/new",
            "complaint-create",
            "بلاغ جديد",
            "message-square-plus",
            ComplaintCreatePage,
            "fleet.self.complaint",
        ),
        route(
            "/complaints/:name",
            "complaint-detail",
            "تفاصيل البلاغ",
            "message-square",
            ComplaintDetailPage,
        ),
    ]);
}
