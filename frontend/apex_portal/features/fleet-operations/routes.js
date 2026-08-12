import AssignmentQueuePage from "./pages/AssignmentQueuePage.vue";
import FuelApprovalQueuePage from "./pages/FuelApprovalQueuePage.vue";
import HandoverQueuePage from "./pages/HandoverQueuePage.vue";
import IncidentDetailPage from "./pages/IncidentDetailPage.vue";
import IncidentQueuePage from "./pages/IncidentQueuePage.vue";
import ProblemDetailPage from "./pages/ProblemDetailPage.vue";
import ProblemQueuePage from "./pages/ProblemQueuePage.vue";
import ReturnQueuePage from "./pages/ReturnQueuePage.vue";
import SupervisorOverviewPage from "./pages/SupervisorOverviewPage.vue";
import VehicleBoardPage from "./pages/VehicleBoardPage.vue";
import VehicleWorkspacePage from "./pages/VehicleWorkspacePage.vue";
import "./styles.css";
const nav = new Set([
    "/",
    "/vehicles",
    "/assignments",
    "/handovers",
    "/returns",
    "/fuel-approvals",
    "/incidents",
    "/problems",
]);
const route = (path, name, label, icon, component, capability = "fleet.operations.read") =>
    Object.freeze({
        path,
        name,
        label,
        icon,
        component,
        feature: "fleet-operations",
        capability,
        meta: Object.freeze({ navigation: nav.has(path), label, icon }),
    });
export function createFleetOperationsRoutes() {
    return Object.freeze([
        route("/", "supervisor-overview", "نظرة عامة", "layout-dashboard", SupervisorOverviewPage),
        route("/vehicles", "vehicle-board", "المركبات", "truck", VehicleBoardPage),
        route(
            "/vehicles/:vehicle",
            "vehicle-workspace",
            "مساحة المركبة",
            "panel-right",
            VehicleWorkspacePage,
        ),
        route(
            "/assignments",
            "assignment-queue",
            "الإسناد",
            "user-round-check",
            AssignmentQueuePage,
        ),
        route("/handovers", "handover-queue", "الاستلام", "clipboard-check", HandoverQueuePage),
        route("/returns", "return-queue", "الإرجاع", "undo-2", ReturnQueuePage),
        route(
            "/fuel-approvals",
            "fuel-approval-queue",
            "اعتماد الوقود",
            "fuel",
            FuelApprovalQueuePage,
            "fleet.operations.fuel",
        ),
        route("/incidents", "incident-queue", "الحوادث", "triangle-alert", IncidentQueuePage),
        route(
            "/incidents/:name",
            "incident-detail",
            "تفاصيل الحادث",
            "file-warning",
            IncidentDetailPage,
        ),
        route("/problems", "problem-queue", "المشكلات", "messages-square", ProblemQueuePage),
        route(
            "/problems/:name",
            "problem-detail",
            "تفاصيل المشكلة",
            "message-square",
            ProblemDetailPage,
        ),
    ]);
}
