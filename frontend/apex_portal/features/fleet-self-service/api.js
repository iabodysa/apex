import { createResource } from "frappe-ui";

export const FLEET_SELF_METHODS = Object.freeze({
    context: "apex.salis.api.fleet_employee.get_context",
    vehicle: "apex.salis.api.fleet_employee.get_my_vehicle",
    handovers: "apex.salis.api.fleet_employee.get_my_handovers",
    receiveVehicle: "apex.salis.api.fleet_employee.receive_vehicle",
    returnVehicle: "apex.salis.api.fleet_employee.return_vehicle",
    quota: "apex.salis.api.fleet_employee.get_my_fuel_quota",
    fuel: "apex.salis.api.fleet_employee.get_my_fuel_requests",
    stations: "apex.salis.api.fleet_employee.get_fuel_stations",
    requestFuel: "apex.salis.api.fleet_employee.submit_fuel_request",
    requestAdditionalFuel: "apex.salis.api.fleet_employee.submit_additional_fuel_request",
    incidents: "apex.salis.api.fleet_employee.get_my_incidents",
    reportIncident: "apex.salis.api.fleet_employee.report_incident",
    complaints: "apex.salis.api.fleet_employee.get_my_complaints",
    complaint: "apex.salis.api.fleet_employee.get_complaint",
    createComplaint: "apex.salis.api.fleet_employee.create_complaint",
    replyComplaint: "apex.salis.api.fleet_employee.reply_to_complaint",
});

const READS = new Set([
    "context",
    "vehicle",
    "handovers",
    "quota",
    "fuel",
    "stations",
    "incidents",
    "complaints",
    "complaint",
]);

export function createFleetSelfResources(factory = createResource) {
    return Object.freeze(
        Object.fromEntries(
            Object.entries(FLEET_SELF_METHODS).map(([name, url]) => [
                name,
                factory({ url, method: READS.has(name) ? "GET" : "POST", auto: false }),
            ]),
        ),
    );
}
