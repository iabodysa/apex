import "./styles.css";
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
        route("/", "supervisor-overview", "نظرة عامة", "layout-dashboard", pages.overview),
        route("/vehicles", "vehicle-board", "المركبات", "truck", pages.vehicles),
        route(
            "/vehicles/:vehicle",
            "vehicle-workspace",
            "مساحة المركبة",
            "panel-right",
            pages.vehicle,
        ),
        route(
            "/assignments",
            "assignment-queue",
            "الإسناد",
            "user-round-check",
            pages.assignments,
        ),
        route("/handovers", "handover-queue", "الاستلام", "clipboard-check", pages.handovers),
        route(
            "/handovers/:name",
            "handover-detail",
            "تفاصيل استلام المركبة",
            "clipboard-check",
            pages.handover,
        ),
        route("/returns", "return-queue", "الإرجاع", "undo-2", pages.returns),
        route(
            "/returns/:name",
            "return-detail",
            "تفاصيل إرجاع المركبة",
            "undo-2",
            pages.handover,
        ),
        route(
            "/fuel-approvals",
            "fuel-approval-queue",
            "اعتماد الوقود",
            "fuel",
            pages.fuel,
            "fleet.operations.fuel",
        ),
        route("/incidents", "incident-queue", "الحوادث", "triangle-alert", pages.incidents),
        route(
            "/incidents/:name",
            "incident-detail",
            "تفاصيل الحادث",
            "file-warning",
            pages.incident,
        ),
        route("/problems", "problem-queue", "المشكلات", "messages-square", pages.problems),
        route(
            "/problems/:name",
            "problem-detail",
            "تفاصيل المشكلة",
            "message-square",
            pages.problem,
        ),
    ]);
}
