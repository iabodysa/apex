// Copyright (c) 2026, afmcoltd
import { call } from "@shared/call";

export { call };

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
