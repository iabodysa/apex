// Copyright (c) 2026, AFMCO and contributors
// The supervisor portal's method-call layer is the cross-portal @shared/call wrapper
// (frappe-ui's frappeRequest, CSRF-signed from window.csrf_token). Re-exported here so
// call sites import from a stable local path.
import { call } from "@shared/call";

export { call };

// The canonical dotted path to the whitelisted backend module.
export const API = "apex.salis.api.route_supervisor";

function callApi(method, opts = {}) {
  return call(API + "." + method, opts);
}

export const getSupervisorContext = () => callApi("get_supervisor_context");
export const getRouteStops = (route_plan) => callApi("get_route_stops", { args: { route_plan } });
export const getTripBoarding = (dispatch_trip) =>
  callApi("get_trip_boarding", { args: { dispatch_trip } });
export const getTripDriverPosition = (dispatch_trip) =>
  callApi("get_trip_driver_position", { args: { dispatch_trip } });
export const getActiveDriverPositions = () => callApi("get_active_driver_positions");
export const approveRoutePlan = (name) =>
  callApi("approve_route_plan", { args: { name }, type: "POST" });
export const rejectRoutePlan = (name, reason) =>
  callApi("reject_route_plan", { args: { name, reason }, type: "POST" });
