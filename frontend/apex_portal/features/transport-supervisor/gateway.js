async function unwrap(call, method, params) {
  const response = params === undefined ? await call(method) : await call(method, params);
  return response?.message ?? response;
}

export function createTransportSupervisorGateway(call) {
  return Object.freeze({
    requests: () => unwrap(call, "apex.salis.api.route_supervisor.get_transport_requests"),
    shifts: () => unwrap(call, "apex.salis.api.route_supervisor.get_shift_routes"),
    plans: () => unwrap(call, "apex.salis.api.route_supervisor.get_route_plans"),
    plan: (name) => unwrap(call, "apex.salis.api.route_supervisor.get_route_plan", { name }),
    createPlan: (values) => unwrap(call, "frappe.client.insert", { doc: { doctype: "Route Plan", ...values } }),
    trips: () => unwrap(call, "apex.salis.api.route_supervisor.get_dispatch_trips"),
    trip: (name) => unwrap(call, "apex.salis.api.route_supervisor.get_dispatch_trip", { name }),
    map: () => unwrap(call, "apex.salis.api.route_supervisor.get_active_driver_positions"),
    history: () => unwrap(call, "apex.salis.api.route_supervisor.get_movement_history"),
    applyRequestAction: (name, action) => unwrap(call, "apex.salis.api.route_supervisor.apply_transport_request_action", { name, action }),
    applyTripAction: (name, action) => unwrap(call, "apex.salis.api.route_supervisor.apply_dispatch_trip_action", { name, action }),
  });
}
