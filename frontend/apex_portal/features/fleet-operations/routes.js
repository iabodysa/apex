import "./styles.css";
import { __ } from "../../core/i18n.js";
const pages = Object.freeze({
    overview: () => import("./pages/SupervisorOverviewPage.vue"),
    vehicles: () => import("./pages/VehicleBoardPage.vue"),
    vehicle: () => import("./pages/VehicleWorkspacePage.vue"),
    assignments: () => import("./pages/AssignmentQueuePage.vue"),
    handovers: () => import("./pages/HandoverQueuePage.vue"),
    handover: () => import("./pages/HandoverDetailPage.vue"),
    returns: () => import("./pages/ReturnQueuePage.vue"),
    fuel: () => import("./pages/FuelApprovalQueuePage.vue"),
    incidents: () => import("./pages/IncidentQueuePage.vue"),
    incident: () => import("./pages/IncidentDetailPage.vue"),
    problems: () => import("./pages/ProblemQueuePage.vue"),
    problem: () => import("./pages/ProblemDetailPage.vue"),
});
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
        route("/", "supervisor-overview", __("Overview"), "lucide-layout-dashboard", pages.overview),
        route("/vehicles", "vehicle-board", __("Vehicles"), "lucide-truck", pages.vehicles),
        route(
            "/vehicles/:vehicle",
            "vehicle-workspace",
            __("Vehicle Workspace"),
            "lucide-panel-right",
            pages.vehicle,
        ),
        route(
            "/assignments",
            "assignment-queue",
            __("Assignment"),
            "lucide-user-round-check",
            pages.assignments,
        ),
        route("/handovers", "handover-queue", __("Handover intake"), "lucide-clipboard-check", pages.handovers),
        route(
            "/handovers/:name",
            "handover-detail",
            __("Vehicle Receipt Details"),
            "lucide-clipboard-check",
            pages.handover,
        ),
        route("/returns", "return-queue", __("Vehicle Returns"), "lucide-undo-2", pages.returns),
        route(
            "/returns/:name",
            "return-detail",
            __("Vehicle Return Details"),
            "lucide-undo-2",
            pages.handover,
        ),
        route(
            "/fuel-approvals",
            "fuel-approval-queue",
            __("Fuel Approval"),
            "lucide-fuel",
            pages.fuel,
            "fleet.operations.fuel",
        ),
        route("/incidents", "incident-queue", __("Incidents"), "lucide-triangle-alert", pages.incidents),
        route(
            "/incidents/:name",
            "incident-detail",
            __("Accident Details"),
            "lucide-file-warning",
            pages.incident,
        ),
        route("/problems", "problem-queue", __("Problems"), "lucide-messages-square", pages.problems),
        route(
            "/problems/:name",
            "problem-detail",
            __("Problem Details"),
            "lucide-message-square",
            pages.problem,
        ),
    ]);
}
