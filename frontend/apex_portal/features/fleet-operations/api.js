import { createResource } from "frappe-ui";

export const FLEET_OPERATIONS_METHODS = Object.freeze({
    overview: "apex.salis.api.fleet_os.get_operations_overview",
    vehicles: "apex.salis.api.fleet_os.get_fleet_os",
    vehicleTimeline: "apex.salis.api.fleet_os.get_vehicle_timeline",
    assignments: "apex.salis.api.fleet_os.get_assignment_queue",
    handovers: "apex.salis.api.fleet_os.get_handover_queue",
    returns: "apex.salis.api.fleet_os.get_return_queue",
    fuelQueue: "apex.salis.api.fuel_console.get_pending_fuel_requests",
    approveFuel: "apex.salis.api.fuel_console.approve_fuel_request",
    rejectFuel: "apex.salis.api.fuel_console.reject_fuel_request",
    incidents: "apex.salis.api.fleet_os.get_incident_queue",
    incident: "apex.salis.api.fleet_os.get_incident_detail",
    problems: "apex.salis.api.fleet_os.get_problem_queue",
    problem: "apex.salis.api.fleet_os.get_problem_detail",
    reassign: "apex.salis.api.fleet_os.reassign",
    stop: "apex.salis.api.fleet_os.stop_vehicle",
    workshopIn: "apex.salis.api.fleet_os.workshop_in",
    workshopOut: "apex.salis.api.fleet_os.workshop_out",
    recover: "apex.salis.api.fleet_os.recover",
});
const READS = new Set([
    "overview",
    "vehicles",
    "vehicleTimeline",
    "assignments",
    "handovers",
    "returns",
    "fuelQueue",
    "incidents",
    "incident",
    "problems",
    "problem",
]);
export function createFleetOperationsResources(factory = createResource) {
    return Object.freeze(
        Object.fromEntries(
            Object.entries(FLEET_OPERATIONS_METHODS).map(([name, url]) => [
                name,
                factory({ url, method: READS.has(name) ? "GET" : "POST", auto: false }),
            ]),
        ),
    );
}
